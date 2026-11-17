import asyncio

from langgraph.store.memory import InMemoryStore

from agent_service.harness.memory import MEMORY_INTRO, PROMPT_MEMORY_LIMIT, MemoryToolkit
from agent_service.memory.user_memories import UserMemoryRepository

ALICE_CONFIG = {"configurable": {"user_id": "alice"}}
CLOCK_TICK_SECONDS = 0.02


async def test_prompt_lists_newest_memories_up_to_the_limit() -> None:
    store = InMemoryStore()
    repository = UserMemoryRepository(store)
    for index in range(PROMPT_MEMORY_LIMIT + 2):
        await repository.save("alice", f"fact {index}")
        await asyncio.sleep(CLOCK_TICK_SECONDS)

    text = await MemoryToolkit(store).prompt_text(ALICE_CONFIG)

    lines = text.splitlines()
    assert lines[0] == MEMORY_INTRO
    assert lines[1] == f"- fact {PROMPT_MEMORY_LIMIT + 1}"
    assert len(lines) == 1 + PROMPT_MEMORY_LIMIT
    assert "- fact 0" not in lines


async def test_prompt_is_empty_without_user_or_memories() -> None:
    store = InMemoryStore()
    await UserMemoryRepository(store).save("bob", "Bob only")
    toolkit = MemoryToolkit(store)

    assert await toolkit.prompt_text(ALICE_CONFIG) == ""
    assert await toolkit.prompt_text({"configurable": {}}) == ""
    assert await toolkit.prompt_text({}) == ""


def test_toolkit_exposes_both_memory_tools() -> None:
    names = [tool.name for tool in MemoryToolkit(InMemoryStore()).tools]

    assert names == ["search_memory", "save_memory"]
