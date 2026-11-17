"""Agent yang bisa memanggil tool berulang kali sampai bisa menjawab (loop ReAct)."""

from collections.abc import Sequence
from typing import Final, NotRequired, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, ToolException
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.managed import RemainingSteps
from langgraph.prebuilt import ToolNode, tools_condition

from agent_service.agents.base import AgentGraph, BaseAgent, Checkpointer
from agent_service.harness.context import ContextBuilder
from agent_service.harness.context_policy import ContextPolicy, ContextWindow
from agent_service.harness.skills.toolkit import SkillToolkit

AGENT_NODE: Final = "agent"
TOOLS_NODE: Final = "tools"
# Satu langkah untuk menjalankan tool dan satu lagi untuk menjawab. Jika sisa langkah kurang dari
# ini, tool call baru tidak akan pernah sempat dijawab sebelum `recursion_limit` tercapai.
MIN_REMAINING_STEPS: Final = 2
STEP_LIMIT_MESSAGE: Final = "Sorry, I need more steps to finish this request."


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
    punya skill aktif (FR-38). Tanpa tool sama sekali, graph-nya `agent → END`.
    """

    def __init__(
        self,
        agent_id: str,
        description: str,
        tools: Sequence[BaseTool],
        context: ContextBuilder,
        skills: SkillToolkit | None = None,
        context_policy: ContextPolicy | None = None,
    ) -> None:
        """Inisialisasi agent.

        Args:
            agent_id: ID agent di registry.
            description: Deskripsi untuk `/info`.
            tools: Tool yang boleh dipanggil model. Dibuat sekali dan dipakai semua graph.
            context: Perakit system prompt (instruksi agent, project, lingkungan).
            skills: Toolkit skill. `None` berarti agent tidak bisa memakai skill.
            context_policy: Anggaran token riwayat. Default: `ContextPolicy()` (16.000 token).
        """
        super().__init__(agent_id=agent_id, description=description)
        self._policy = ContextPolicy() if context_policy is None else context_policy
        self._tools = list(tools)
        self._skills = skills
        self._context = context if skills is None else context.with_skills(skills)

    def build(self, model: BaseChatModel, checkpointer: Checkpointer) -> AgentGraph:
        """Compile graph `agent → tools → agent`, yang berhenti saat model tidak memanggil tool.

        Args:
            model: Chat model untuk graph ini. Tools di-bind ke model ini.
            checkpointer: Saver tempat riwayat thread disimpan.

        Returns:
            Graph yang sudah di-compile.
        """
        return self._graph_builder(model).compile(checkpointer=checkpointer)

    def build_stateless(self, model: BaseChatModel) -> AgentGraph:
        """Compile graph yang sama tanpa checkpoint, untuk dipakai sebagai sub-agent.

        Setiap pemanggilan dimulai dari state kosong dan tidak menulis checkpoint, walaupun
        dijalankan di dalam node graph lain yang punya checkpointer.

        Args:
            model: Chat model untuk graph ini.

        Returns:
            Graph tanpa checkpointer.
        """
        return self._graph_builder(model).compile(checkpointer=False)

    def _graph_builder(self, model: BaseChatModel) -> StateGraph:
        """Susun graph `agent → tools → agent` untuk `model`, belum di-compile."""
        all_tools = self._all_tools()
        base_model = model.bind_tools(self._tools) if self._tools else model
        skill_model = model.bind_tools(all_tools) if self._skills is not None else base_model

        # Closure, bukan method: satu instance agent membangun graph untuk beberapa model.
        async def call_model(state: ToolCallingState, config: RunnableConfig) -> ModelTurnUpdate:
            window = await self._policy.prepare(
                model,
                state["messages"],
                state.get("summary", ""),
                state.get("summarized_through", ""),
            )
            prompt = self._context.system_message(config, window.summary)
            uses_skills = self._skills is not None and bool(self._skills.tools_for(config))
            bound_model = skill_model if uses_skills else base_model
            response = await bound_model.ainvoke([prompt, *window.messages])
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
        # pesan error. Bug lain tetap menggagalkan run supaya terlihat.
        builder.add_node(TOOLS_NODE, ToolNode(all_tools, handle_tool_errors=(ToolException,)))
        builder.add_conditional_edges(AGENT_NODE, tools_condition)
        builder.add_edge(TOOLS_NODE, AGENT_NODE)
        return builder

    def _all_tools(self) -> list[BaseTool]:
        """Tool agent ditambah tool skill, yang semuanya didaftarkan di `ToolNode`."""
        skill_tools = [] if self._skills is None else self._skills.tools
        return [*self._tools, *skill_tools]


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
