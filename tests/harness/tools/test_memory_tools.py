import pytest
from langchain_core.tools import BaseTool, ToolException
from langgraph.store.memory import InMemoryStore

from agent_service.harness.tools.memory import (
    MEMORY_UNAVAILABLE_TEXT,
    NO_MATCHES_TEXT,
    create_memory_tools,
    is_approval,
)
from agent_service.memory.user_memories import UserMemoryRepository

USER_CONFIG = {"configurable": {"user_id": "alice"}}


@pytest.fixture
def repository() -> UserMemoryRepository:
    return UserMemoryRepository(InMemoryStore())


def tools_by_name(repository: UserMemoryRepository) -> dict[str, BaseTool]:
    return {tool.name: tool for tool in create_memory_tools(repository)}


@pytest.mark.parametrize(
    "reply", ["yes", "Yes!", "y", "ok", "OK, save it", "ya", "Iya, simpan saja", "boleh dong"]
)
def test_approving_replies(reply: str) -> None:
    assert is_approval(reply)


@pytest.mark.parametrize(
    "reply",
    ["no", "", "   ", "please", "ya tapi ganti jadi kopi", "yes but not that", "nanti", None, 1],
)
def test_other_replies_are_not_approval(reply: object) -> None:
    assert not is_approval(reply)


def test_tool_schemas_hide_the_run_config(repository: UserMemoryRepository) -> None:
    tools = tools_by_name(repository)

    assert set(tools) == {"search_memory", "save_memory"}
    assert set(tools["search_memory"].args) == {"query"}
    assert set(tools["save_memory"].args) == {"memory"}


async def test_search_returns_matching_memories_of_the_run_user(
    repository: UserMemoryRepository,
) -> None:
    await repository.save("alice", "Prefers green tea")
    await repository.save("bob", "Prefers black tea")
    search = tools_by_name(repository)["search_memory"]

    found = await search.ainvoke({"query": "tea"}, config=USER_CONFIG)
    missing = await search.ainvoke({"query": "coffee"}, config=USER_CONFIG)

    assert found == "- Prefers green tea"
    assert missing == NO_MATCHES_TEXT


@pytest.mark.parametrize("tool_name", ["search_memory", "save_memory"])
async def test_tools_need_a_user(repository: UserMemoryRepository, tool_name: str) -> None:
    tool = tools_by_name(repository)[tool_name]
    arguments = {"query": "tea"} if tool_name == "search_memory" else {"memory": "Likes tea"}

    with pytest.raises(ToolException, match=MEMORY_UNAVAILABLE_TEXT):
        await tool.ainvoke(arguments, config={"configurable": {}})


async def test_invalid_memory_fails_before_asking_the_user(
    repository: UserMemoryRepository,
) -> None:
    save = tools_by_name(repository)["save_memory"]

    # Di luar graph, interrupt() akan gagal dengan error lain. ToolException membuktikan validasi
    # terjadi sebelum user ditanya.
    with pytest.raises(ToolException, match="empty"):
        await save.ainvoke({"memory": "   "}, config=USER_CONFIG)
