from datetime import UTC, datetime
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import PrivateAttr

from agent_service.agents.chatbot import CHATBOT_AGENT_ID, ChatbotAgent
from agent_service.harness.context import ContextBuilder
from agent_service.llm.fake import FakeModel


def thread_config(thread_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id}}


def test_default_identity() -> None:
    agent = ChatbotAgent()

    assert agent.agent_id == CHATBOT_AGENT_ID
    assert agent.description


async def test_reply_comes_from_given_model() -> None:
    graph = ChatbotAgent().build(FakeModel(responses=["Halo!"]), InMemorySaver())

    result = await graph.ainvoke({"messages": [HumanMessage("Hai")]}, thread_config("t1"))

    reply = result["messages"][-1]
    assert isinstance(reply, AIMessage)
    assert reply.content == "Halo!"


async def test_history_is_kept_per_thread() -> None:
    graph = ChatbotAgent().build(FakeModel(responses=["satu", "dua"]), InMemorySaver())

    await graph.ainvoke({"messages": [HumanMessage("pertama")]}, thread_config("t1"))
    result = await graph.ainvoke({"messages": [HumanMessage("kedua")]}, thread_config("t1"))

    contents = [message.content for message in result["messages"]]
    assert contents == ["pertama", "satu", "kedua", "dua"]


async def test_threads_do_not_share_history() -> None:
    graph = ChatbotAgent().build(FakeModel(), InMemorySaver())

    await graph.ainvoke({"messages": [HumanMessage("thread satu")]}, thread_config("t1"))
    result = await graph.ainvoke({"messages": [HumanMessage("thread dua")]}, thread_config("t2"))

    assert len(result["messages"]) == 2


async def test_graph_streams_tokens_from_model() -> None:
    graph = ChatbotAgent().build(FakeModel(responses=["Halo dunia"]), InMemorySaver())

    tokens: list[str] = []
    async for chunk, _metadata in graph.astream(
        {"messages": [HumanMessage("Hai")]}, thread_config("t1"), stream_mode="messages"
    ):
        if isinstance(chunk, BaseMessage) and chunk.content:
            tokens.append(str(chunk.content))

    assert tokens == ["Halo ", "dunia"]


class PromptRecorder(FakeModel):
    """FakeModel yang merekam message yang diterima di setiap panggilan."""

    _seen: list[list[BaseMessage]] = PrivateAttr(default_factory=list)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> ChatResult:
        self._seen.append(list(messages))
        return super()._generate(messages, stop, run_manager, **kwargs)

    @property
    def seen(self) -> list[list[BaseMessage]]:
        return self._seen


FIXED_NOW = datetime(2026, 11, 16, 8, 0, tzinfo=UTC)


async def test_model_gets_environment_prompt_that_is_not_stored() -> None:
    model = PromptRecorder(responses=["Halo!"])
    agent = ChatbotAgent(context=ContextBuilder(clock=lambda: FIXED_NOW))

    result = await agent.build(model, InMemorySaver()).ainvoke(
        {"messages": [HumanMessage("Tanggal berapa?")]}, thread_config("t1")
    )

    [prompt, question] = model.seen[0]
    assert isinstance(prompt, SystemMessage)
    assert prompt.content == (
        "## Environment\nCurrent date: Monday, November 16, 2026. Timezone: UTC (UTC+00:00)."
    )
    assert question.content == "Tanggal berapa?"
    assert not any(isinstance(m, SystemMessage) for m in result["messages"])


async def test_project_instructions_are_added_to_the_prompt() -> None:
    model = PromptRecorder(responses=["Halo!"])
    config = thread_config("t1")
    config["configurable"]["project_instructions"] = "Jawab dalam Bahasa Indonesia."

    await (
        ChatbotAgent()
        .build(model, InMemorySaver())
        .ainvoke({"messages": [HumanMessage("Hi")]}, config)
    )

    prompt = str(model.seen[0][0].content)
    assert "## Project instructions\nJawab dalam Bahasa Indonesia." in prompt
