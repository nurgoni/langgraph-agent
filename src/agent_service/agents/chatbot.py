"""Agent minimal: satu panggilan LLM dengan riwayat percakapan."""

from typing import Final

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, MessagesState, StateGraph

from agent_service.agents.base import AgentGraph, BaseAgent, Checkpointer

CHATBOT_AGENT_ID: Final = "chatbot"
CHATBOT_DESCRIPTION: Final = "A simple chatbot that answers using the conversation history."
CHAT_NODE: Final = "chat"


class ChatbotAgent(BaseAgent):
    """Agent referensi: graph `START → chat → END` yang menyimpan riwayat lewat checkpointer.

    Node-nya async, jadi graph dijalankan lewat API async (`ainvoke`, `astream`).

    >>> import asyncio
    >>> from langgraph.checkpoint.memory import InMemorySaver
    >>> from agent_service.llm.fake import FakeModel
    >>> graph = ChatbotAgent().build(FakeModel(responses=["Halo!"]), InMemorySaver())
    >>> config = {"configurable": {"thread_id": "t1"}}
    >>> result = asyncio.run(graph.ainvoke({"messages": [("human", "Hai")]}, config))
    >>> result["messages"][-1].content
    'Halo!'
    """

    def __init__(
        self, agent_id: str = CHATBOT_AGENT_ID, description: str = CHATBOT_DESCRIPTION
    ) -> None:
        """Inisialisasi chatbot.

        Args:
            agent_id: ID agent di registry.
            description: Deskripsi untuk `/info`.
        """
        super().__init__(agent_id=agent_id, description=description)

    def build(self, model: BaseChatModel, checkpointer: Checkpointer) -> AgentGraph:
        """Compile graph satu node yang memanggil `model` dengan seluruh riwayat thread.

        Args:
            model: Chat model untuk graph ini.
            checkpointer: Saver tempat riwayat thread disimpan.

        Returns:
            Graph chatbot yang sudah di-compile.
        """

        # Closure, bukan method: satu instance agent membangun graph untuk beberapa model.
        async def chat(state: MessagesState) -> MessagesState:
            response = await model.ainvoke(state["messages"])
            return {"messages": [response]}

        # pyrefly tidak mengenali TypedDict sebagai TypedDictLike milik LangGraph.
        builder = StateGraph(MessagesState)  # pyrefly: ignore[bad-specialization]
        builder.add_node(CHAT_NODE, chat)
        builder.add_edge(START, CHAT_NODE)
        builder.add_edge(CHAT_NODE, END)
        return builder.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    import asyncio

    from langgraph.checkpoint.memory import InMemorySaver

    from agent_service.llm.fake import FakeModel

    async def _demo() -> None:
        graph = ChatbotAgent().build(FakeModel(), InMemorySaver())
        result = await graph.ainvoke(
            {"messages": [("human", "Halo")]}, {"configurable": {"thread_id": "demo"}}
        )
        print(result["messages"][-1].content)

    asyncio.run(_demo())
