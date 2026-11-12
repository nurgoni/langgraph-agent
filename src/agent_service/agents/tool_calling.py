"""Agent yang bisa memanggil tool berulang kali sampai bisa menjawab (loop ReAct)."""

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Final

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.tools import BaseTool, ToolException
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.managed import RemainingSteps
from langgraph.prebuilt import ToolNode, tools_condition

from agent_service.agents.base import AgentGraph, BaseAgent, Checkpointer

AGENT_NODE: Final = "agent"
TOOLS_NODE: Final = "tools"
DATE_FORMAT: Final = "%B %d, %Y"
DATE_PLACEHOLDER: Final = "current_date"
# Satu langkah untuk menjalankan tool dan satu lagi untuk menjawab. Jika sisa langkah kurang dari
# ini, tool call baru tidak akan pernah sempat dijawab sebelum `recursion_limit` tercapai.
MIN_REMAINING_STEPS: Final = 2
STEP_LIMIT_MESSAGE: Final = "Sorry, I need more steps to finish this request."

type Clock = Callable[[], datetime]


class ToolCallingState(MessagesState):
    """State graph: riwayat message ditambah sisa langkah sebelum `recursion_limit`."""

    remaining_steps: RemainingSteps


def local_now() -> datetime:
    """Waktu lokal saat ini, dihitung setiap kali dipanggil (bukan saat import)."""
    return datetime.now().astimezone()


class ToolCallingAgent(BaseAgent):
    """Agent dengan daftar tools dan system prompt yang bisa diatur.

    Model memutuskan tool mana yang dipanggil. Hasil tool dikembalikan ke model sampai model
    menjawab tanpa tool call. Research assistant adalah satu instance class ini, dan agent RAG
    nantinya cukup menjadi instance lain dengan tool retriever.
    """

    def __init__(
        self,
        agent_id: str,
        description: str,
        tools: Sequence[BaseTool],
        system_prompt: str,
        clock: Clock = local_now,
    ) -> None:
        """Inisialisasi agent.

        Args:
            agent_id: ID agent di registry.
            description: Deskripsi untuk `/info`.
            tools: Tool yang boleh dipanggil model. Dibuat sekali dan dipakai semua graph.
            system_prompt: Instruksi untuk model. Boleh berisi `{current_date}`, yang diisi tanggal
                hari ini setiap kali model dipanggil.
            clock: Sumber waktu, bisa diganti di test.
        """
        super().__init__(agent_id=agent_id, description=description)
        self._tools = list(tools)
        self._system_prompt = system_prompt
        self._clock = clock

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
        model_with_tools = model.bind_tools(self._tools)

        # Closure, bukan method: satu instance agent membangun graph untuk beberapa model.
        async def call_model(state: ToolCallingState) -> dict[str, list[AIMessage]]:
            prompt = SystemMessage(content=self._render_system_prompt())
            response = await model_with_tools.ainvoke([prompt, *state["messages"]])
            if response.tool_calls and state["remaining_steps"] < MIN_REMAINING_STEPS:
                return {"messages": [AIMessage(id=response.id, content=STEP_LIMIT_MESSAGE)]}
            return {"messages": [response]}

        # pyrefly tidak mengenali TypedDict sebagai TypedDictLike milik LangGraph.
        builder = StateGraph(ToolCallingState)  # pyrefly: ignore[bad-specialization]
        builder.add_node(AGENT_NODE, call_model)
        # Hanya ToolException (input salah, pencarian gagal) yang dikembalikan ke model sebagai
        # pesan error. Bug lain tetap menggagalkan run supaya terlihat.
        builder.add_node(TOOLS_NODE, ToolNode(self._tools, handle_tool_errors=(ToolException,)))
        builder.add_edge(START, AGENT_NODE)
        builder.add_conditional_edges(AGENT_NODE, tools_condition)
        builder.add_edge(TOOLS_NODE, AGENT_NODE)
        return builder

    def _render_system_prompt(self) -> str:
        """System prompt dengan tanggal hari ini."""
        current_date = self._clock().strftime(DATE_FORMAT)
        return self._system_prompt.format(**{DATE_PLACEHOLDER: current_date})


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
        agent = ToolCallingAgent("demo", "Demo", [calculator], "Today is {current_date}.")
        graph = agent.build(model, InMemorySaver())
        result = await graph.ainvoke(
            {"messages": [("human", "12 * 7?")]}, {"configurable": {"thread_id": "demo"}}
        )
        for message in result["messages"]:
            print(type(message).__name__, message.content)

    asyncio.run(_demo())
