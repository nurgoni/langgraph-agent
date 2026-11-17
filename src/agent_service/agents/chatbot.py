"""Agent minimal: satu panggilan LLM dengan riwayat percakapan, plus skill jika project aktif."""

from typing import Final

from agent_service.agents.tool_calling import ToolCallingAgent
from agent_service.harness.context import ContextBuilder
from agent_service.harness.context_policy import ContextPolicy
from agent_service.harness.skills.toolkit import SkillToolkit

CHATBOT_AGENT_ID: Final = "chatbot"
CHATBOT_DESCRIPTION: Final = "A simple chatbot that answers using the conversation history."


class ChatbotAgent(ToolCallingAgent):
    """Agent referensi tanpa tool bawaan: `START → agent → END`, riwayat lewat checkpointer.

    Ditulis di atas `ToolCallingAgent` supaya chatbot bisa memakai skill (F28): jika project punya
    skill aktif, `load_skill` di-bind dan graph bisa memanggilnya. Tanpa skill aktif, model
    dipanggil sekali tanpa tool, sama seperti v1. Node-nya async, jadi graph dijalankan lewat API
    async (`ainvoke`, `astream`).

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
        self,
        agent_id: str = CHATBOT_AGENT_ID,
        description: str = CHATBOT_DESCRIPTION,
        context: ContextBuilder | None = None,
        skills: SkillToolkit | None = None,
        context_policy: ContextPolicy | None = None,
        use_memory: bool = False,
    ) -> None:
        """Inisialisasi chatbot.

        Args:
            agent_id: ID agent di registry.
            description: Deskripsi untuk `/info`.
            context: Perakit system prompt. Default: tanpa instruksi agent.
            skills: Toolkit skill. `None` berarti chatbot tidak bisa memakai skill.
            context_policy: Anggaran token riwayat. Default: `ContextPolicy()`.
            use_memory: Pakai long-term memory user (FR-40) jika registry punya store.
        """
        super().__init__(
            agent_id=agent_id,
            description=description,
            tools=[],
            context=ContextBuilder() if context is None else context,
            skills=skills,
            context_policy=context_policy,
            use_memory=use_memory,
        )


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
