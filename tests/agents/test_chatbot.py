from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

from agent_service.agents.chatbot import CHATBOT_AGENT_ID, ChatbotAgent
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
