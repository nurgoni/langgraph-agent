"""Agent yang bisa memanggil tool berulang kali sampai bisa menjawab (loop ReAct)."""

from collections.abc import Mapping, Sequence
from typing import Any, Final, NotRequired, Protocol, TypedDict

from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.managed import RemainingSteps
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.store.base import BaseStore

from agent_service.agents.base import AgentGraph, BaseAgent, Checkpointer
from agent_service.agents.tools.data import DataToolkit
from agent_service.harness.context import ContextBuilder
from agent_service.harness.context_policy import ContextPolicy, ContextWindow
from agent_service.harness.memory import MemoryToolkit
from agent_service.harness.skills.toolkit import SkillToolkit
from agent_service.harness.tool_guard import ToolFailureGuard, tool_error_text
from agent_service.harness.workspace import WorkspaceToolkit, with_attachment_notes

AGENT_NODE: Final = "agent"
TOOLS_NODE: Final = "tools"
# Satu langkah untuk menjalankan tool dan satu lagi untuk menjawab. Jika sisa langkah kurang dari
# ini, tool call baru tidak akan pernah sempat dijawab sebelum `recursion_limit` tercapai.
MIN_REMAINING_STEPS: Final = 2
STEP_LIMIT_MESSAGE: Final = "Sorry, I need more steps to finish this request."


class TurnToolkit(Protocol):
    """Kumpulan tool yang di-bind ke model hanya pada giliran tertentu (skill, data)."""

    @property
    def tools(self) -> list[BaseTool]:
        """Semua tool, didaftarkan di `ToolNode` saat compile."""
        ...

    def tools_for(self, config: Mapping[str, Any] | None) -> list[BaseTool]:  # Any: config
        """Tool yang di-bind ke model pada giliran dengan `config` ini."""
        ...


class TurnModels:
    """Model dengan tool giliran ini, di-cache per kombinasi tool supaya `bind_tools` sekali saja.

    Tool tetap (agent, file, memory) selalu di-bind. Tool dari `toolkits` ditambahkan hanya jika
    toolkit-nya mengembalikannya untuk config run ini.
    """

    def __init__(
        self,
        model: BaseChatModel,
        fixed_tools: Sequence[BaseTool],
        toolkits: Sequence[TurnToolkit],
    ) -> None:
        """Inisialisasi pemilih model.

        Args:
            model: Chat model graph ini.
            fixed_tools: Tool yang selalu di-bind.
            toolkits: Toolkit per giliran, urut sesuai urutan tool di model.
        """
        self._model = model
        self._fixed_tools = list(fixed_tools)
        self._toolkits = list(toolkits)
        self._bound: dict[tuple[str, ...], Runnable[LanguageModelInput, AIMessage]] = {}
        # Tool tetap di-bind saat graph dibangun, sama seperti sebelum ada toolkit per giliran.
        self.for_config({})

    @property
    def all_tools(self) -> list[BaseTool]:
        """Semua tool yang mungkin dipanggil, untuk `ToolNode`."""
        return [*self._fixed_tools, *(tool for kit in self._toolkits for tool in kit.tools)]

    def for_config(self, config: RunnableConfig) -> Runnable[LanguageModelInput, AIMessage]:
        """Model dengan tool tetap ditambah tool toolkit yang aktif di run ini."""
        tools = [*self._fixed_tools, *(t for kit in self._toolkits for t in kit.tools_for(config))]
        key = tuple(tool.name for tool in tools)
        if key not in self._bound:
            self._bound[key] = self._model.bind_tools(tools) if tools else self._model
        return self._bound[key]


class ToolCallingState(MessagesState):
    """State graph: riwayat message, ringkasan giliran lama, dan sisa langkah sebelum limit.

    `summary` dan `summarized_through` milik `ContextPolicy` (FR-39). Keduanya belum ada di thread
    baru dan di thread dari versi sebelum F29.
    """

    remaining_steps: RemainingSteps
    summary: NotRequired[str]
    summarized_through: NotRequired[str]


class ModelTurnUpdate(TypedDict):
    """Update node model: jawaban baru, ditambah ringkasan terbaru dari `ContextPolicy`."""

    messages: list[AIMessage]
    summary: str
    summarized_through: str


def model_turn_update(response: AIMessage, window: ContextWindow) -> ModelTurnUpdate:
    """Jawaban model beserta ringkasan dari `window`, untuk disimpan ke state thread."""
    return ModelTurnUpdate(
        messages=[response],
        summary=window.summary,
        summarized_through=window.summarized_through,
    )


class ToolCallingAgent(BaseAgent):
    """Agent dengan daftar tools dan system prompt yang dirakit `ContextBuilder`.

    Model memutuskan tool mana yang dipanggil. Hasil tool dikembalikan ke model sampai model
    menjawab tanpa tool call. Research assistant adalah satu instance class ini, dan agent RAG
    nantinya cukup menjadi instance lain dengan tool retriever. System prompt dirakit ulang di
    setiap panggilan model (FR-37), jadi tanggal dan instruksi project selalu terbaru. Sebelum
    model dipanggil, `ContextPolicy` menjaga riwayat di bawah anggaran token dan meringkas giliran
    lama (FR-39).

    Dengan `skills`, tool `load_skill` dan indeks skill hanya muncul pada giliran yang project-nya
    punya skill aktif (FR-38). Dengan `use_memory` dan store dari `build`, memory terbaru user masuk
    prompt dan tool `search_memory`/`save_memory` selalu di-bind (FR-40). Dengan `files`, tool file
    workspace selalu di-bind, output tool besar dipindah ke workspace, dan path lampiran ditambahkan
    ke pesan human yang dikirim ke model (FR-47, FR-48). Workspace datang dari `HarnessContext` yang
    dikirim service sebagai runtime context. Dengan `data`, tool data hanya di-bind pada giliran
    yang project-nya punya data source (FR-51). Tanpa tool sama sekali, graph-nya `agent → END`.

    Setiap tool call melewati `ToolFailureGuard` (FR-59): tool yang gagal beruntun sebanyak batas di
    satu giliran tidak dijalankan lagi. Jumlah langkah dibatasi `recursion_limit` dari config run,
    dan model yang masih memanggil tool saat sisa langkah habis dijawab `STEP_LIMIT_MESSAGE`.
    """

    def __init__(
        self,
        agent_id: str,
        description: str,
        tools: Sequence[BaseTool],
        context: ContextBuilder,
        skills: SkillToolkit | None = None,
        context_policy: ContextPolicy | None = None,
        use_memory: bool = False,
        files: WorkspaceToolkit | None = None,
        tool_guard: ToolFailureGuard | None = None,
        data: DataToolkit | None = None,
    ) -> None:
        """Inisialisasi agent.

        Args:
            agent_id: ID agent di registry.
            description: Deskripsi untuk `/info`.
            tools: Tool yang boleh dipanggil model. Dibuat sekali dan dipakai semua graph.
            context: Perakit system prompt (instruksi agent, project, lingkungan).
            skills: Toolkit skill. `None` berarti agent tidak bisa memakai skill.
            context_policy: Anggaran token riwayat. Default: `ContextPolicy()` (16.000 token).
            use_memory: Pakai long-term memory user jika `build` menerima store.
            files: Tool file workspace dan offloader output. `None` berarti tanpa workspace.
            tool_guard: Batas kegagalan beruntun per tool. Default: `ToolFailureGuard()` (3).
            data: Tool data source (F39). `None` berarti agent tidak bisa membaca data source.
        """
        super().__init__(agent_id=agent_id, description=description)
        self._policy = ContextPolicy() if context_policy is None else context_policy
        self._tools = list(tools)
        self._skills = skills
        self._context = context if skills is None else context.with_skills(skills)
        self._use_memory = use_memory
        self._files = files
        self._guard = ToolFailureGuard() if tool_guard is None else tool_guard
        self._toolkits: list[TurnToolkit] = [kit for kit in (skills, data) if kit is not None]

    def build(
        self, model: BaseChatModel, checkpointer: Checkpointer, store: BaseStore | None = None
    ) -> AgentGraph:
        """Compile graph `agent → tools → agent`, yang berhenti saat model tidak memanggil tool.

        Args:
            model: Chat model untuk graph ini. Tools di-bind ke model ini.
            checkpointer: Saver tempat riwayat thread disimpan.
            store: Store long-term memory. Dipakai hanya jika agent dibuat dengan `use_memory`.

        Returns:
            Graph yang sudah di-compile.
        """
        memory = MemoryToolkit(store) if self._use_memory and store is not None else None
        return self._graph_builder(model, memory).compile(checkpointer=checkpointer)

    def build_stateless(self, model: BaseChatModel) -> AgentGraph:
        """Compile graph yang sama tanpa checkpoint, untuk dipakai sebagai sub-agent.

        Setiap pemanggilan dimulai dari state kosong dan tidak menulis checkpoint, walaupun
        dijalankan di dalam node graph lain yang punya checkpointer. Sub-agent tidak memakai
        memory, karena interrupt persetujuan `save_memory` tidak bisa dilanjutkan di sini.

        Args:
            model: Chat model untuk graph ini.

        Returns:
            Graph tanpa checkpointer.
        """
        return self._graph_builder(model, None).compile(checkpointer=False)

    def _graph_builder(self, model: BaseChatModel, memory: MemoryToolkit | None) -> StateGraph:
        """Susun graph `agent → tools → agent` untuk `model`, belum di-compile."""
        file_tools = [] if self._files is None else self._files.tools
        agent_tools = [*self._tools, *file_tools, *([] if memory is None else memory.tools)]
        models = TurnModels(model, agent_tools, self._toolkits)
        all_tools = models.all_tools

        # Closure, bukan method: satu instance agent membangun graph untuk beberapa model.
        async def call_model(state: ToolCallingState, config: RunnableConfig) -> ModelTurnUpdate:
            window = await self._policy.prepare(
                model,
                state["messages"],
                state.get("summary", ""),
                state.get("summarized_through", ""),
            )
            memories = "" if memory is None else await memory.prompt_text(config)
            prompt = self._context.system_message(config, window.summary, memories)
            messages = (
                window.messages if self._files is None else with_attachment_notes(window.messages)
            )
            response = await models.for_config(config).ainvoke([prompt, *messages])
            if response.tool_calls and state["remaining_steps"] < MIN_REMAINING_STEPS:
                response = AIMessage(id=response.id, content=STEP_LIMIT_MESSAGE)
            return model_turn_update(response, window)

        # pyrefly tidak mengenali TypedDict sebagai TypedDictLike milik LangGraph.
        builder = StateGraph(ToolCallingState)  # pyrefly: ignore[bad-specialization]
        builder.add_node(AGENT_NODE, call_model)
        builder.add_edge(START, AGENT_NODE)
        if not all_tools:
            builder.add_edge(AGENT_NODE, END)
            return builder
        # Hanya ToolException (input salah, pencarian gagal) yang dikembalikan ke model sebagai
        # pesan error. Bug lain tetap menggagalkan run supaya terlihat. Handler callable, bukan
        # tuple: dengan wrapper, tuple tidak menyaring error yang keluar dari wrapper.
        offloader = None if self._files is None else self._files.offloader
        tool_node = ToolNode(
            all_tools,
            handle_tool_errors=tool_error_text,
            awrap_tool_call=self._guard.around(offloader),
        )
        builder.add_node(TOOLS_NODE, tool_node)
        builder.add_conditional_edges(AGENT_NODE, tools_condition)
        builder.add_edge(TOOLS_NODE, AGENT_NODE)
        return builder


if __name__ == "__main__":
    import asyncio

    from langgraph.checkpoint.memory import InMemorySaver

    from agent_service.agents.tools.calculator import calculator
    from agent_service.llm.fake import FakeModel

    async def _demo() -> None:
        model = FakeModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[{"name": "calculator", "args": {"expression": "12*7"}, "id": "c1"}],
                ),
                "12 x 7 = 84",
            ]
        )
        agent = ToolCallingAgent("demo", "Demo", [calculator], ContextBuilder("Be precise."))
        graph = agent.build(model, InMemorySaver())
        result = await graph.ainvoke(
            {"messages": [("human", "12 * 7?")]}, {"configurable": {"thread_id": "demo"}}
        )
        for message in result["messages"]:
            print(type(message).__name__, message.content)

    asyncio.run(_demo())
