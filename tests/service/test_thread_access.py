import pytest
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import StateSnapshot

from agent_service.agents.base import AgentGraph
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.llm.fake import FakeModel
from agent_service.service.thread_access import (
    ThreadNotFoundError,
    ensure_thread_owner,
    is_new_thread,
    run_metadata,
)

THREAD_ID = "thread-1"
OWNER = "user-a"


def thread_config(thread_id: str = THREAD_ID) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id}}


@pytest.fixture
def graph() -> AgentGraph:
    return ChatbotAgent().build(FakeModel(), InMemorySaver())


@pytest.fixture
async def owned_snapshot(graph: AgentGraph) -> StateSnapshot:
    config: RunnableConfig = {
        "configurable": {"thread_id": THREAD_ID},
        "metadata": run_metadata(OWNER, "chatbot"),
    }
    await graph.ainvoke({"messages": [HumanMessage("hai")]}, config)
    return await graph.aget_state(thread_config())


async def test_unknown_thread_is_new(graph: AgentGraph) -> None:
    snapshot = await graph.aget_state(thread_config("missing"))

    assert is_new_thread(snapshot)
    with pytest.raises(ThreadNotFoundError):
        ensure_thread_owner(snapshot.metadata, "missing", OWNER, "chatbot")


async def test_owner_passes(owned_snapshot: StateSnapshot) -> None:
    assert not is_new_thread(owned_snapshot)
    ensure_thread_owner(owned_snapshot.metadata, THREAD_ID, OWNER, "chatbot")


@pytest.mark.parametrize(("user_id", "agent_id"), [("user-b", "chatbot"), (OWNER, "other")])
async def test_other_user_or_agent_is_not_found(
    owned_snapshot: StateSnapshot, user_id: str, agent_id: str
) -> None:
    with pytest.raises(ThreadNotFoundError) as error_info:
        ensure_thread_owner(owned_snapshot.metadata, THREAD_ID, user_id, agent_id)

    assert error_info.value.thread_id == THREAD_ID
