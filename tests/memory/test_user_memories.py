import asyncio

import pytest
from langgraph.store.memory import InMemoryStore

from agent_service.memory import user_memories
from agent_service.memory.store import StoreProvider
from agent_service.memory.user_memories import (
    MEMORY_TEXT_MAX_CHARS,
    InvalidMemoryError,
    MemoryLimitError,
    MemoryNotFoundError,
    UserMemoryRepository,
    memory_namespace,
)

ALICE = "alice"
BOB = "bob"
# Jam Windows bisa memberi timestamp yang sama untuk dua penyimpanan beruntun.
CLOCK_TICK_SECONDS = 0.02


async def save_in_order(repository: UserMemoryRepository, user_id: str, *texts: str) -> None:
    for text in texts:
        await repository.save(user_id, text)
        await asyncio.sleep(CLOCK_TICK_SECONDS)


@pytest.fixture
def repository() -> UserMemoryRepository:
    return UserMemoryRepository(InMemoryStore())


async def test_saved_memories_are_listed_newest_first(repository: UserMemoryRepository) -> None:
    await save_in_order(repository, ALICE, "Likes green tea", "Works as a data analyst")

    records = await repository.list_memories(ALICE)

    assert [record.text for record in records] == ["Works as a data analyst", "Likes green tea"]
    assert records[0].created_at <= records[0].updated_at


async def test_same_text_updates_instead_of_duplicating(repository: UserMemoryRepository) -> None:
    first = await repository.save(ALICE, "Likes  green tea")
    second = await repository.save(ALICE, "likes GREEN tea ")

    [record] = await repository.list_memories(ALICE)
    assert first.memory_id == second.memory_id == record.memory_id
    assert record.text == "likes GREEN tea"


@pytest.mark.parametrize("text", ["", "   ", "x" * (MEMORY_TEXT_MAX_CHARS + 1)])
async def test_invalid_text_is_rejected(repository: UserMemoryRepository, text: str) -> None:
    with pytest.raises(InvalidMemoryError):
        await repository.save(ALICE, text)

    assert await repository.list_memories(ALICE) == []


async def test_memory_limit_rejects_new_but_allows_updates(
    repository: UserMemoryRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(user_memories, "MAX_MEMORIES_PER_USER", 2)
    await repository.save(ALICE, "one")
    await repository.save(ALICE, "two")

    with pytest.raises(MemoryLimitError):
        await repository.save(ALICE, "three")
    await repository.save(ALICE, "ONE")
    await repository.save(BOB, "three")

    assert len(await repository.list_memories(ALICE)) == 2


async def test_search_ranks_by_matching_words_then_recency(
    repository: UserMemoryRepository,
) -> None:
    await save_in_order(
        repository,
        ALICE,
        "Prefers green tea in the morning",
        "Allergic to peanuts",
        "Drinks black tea at night",
    )

    found = await repository.search(ALICE, "favourite tea in the morning?", limit=5)

    assert [record.text for record in found] == [
        "Prefers green tea in the morning",
        "Drinks black tea at night",
    ]


async def test_search_without_keywords_returns_recent(repository: UserMemoryRepository) -> None:
    await save_in_order(repository, ALICE, "first", "second", "third")

    assert [r.text for r in await repository.search(ALICE, "?", limit=2)] == ["third", "second"]
    assert await repository.search(ALICE, "nothing matches", limit=2) == []


async def test_users_never_see_each_others_memories(repository: UserMemoryRepository) -> None:
    alice_memory = await repository.save(ALICE, "Alice secret")
    await repository.save("ali", "Prefix user")

    assert await repository.list_memories(BOB) == []
    assert await repository.search(BOB, "secret", limit=5) == []
    assert [r.text for r in await repository.list_memories(ALICE)] == ["Alice secret"]
    with pytest.raises(MemoryNotFoundError):
        await repository.delete(BOB, alice_memory.memory_id)
    assert len(await repository.list_memories(ALICE)) == 1


async def test_limit_keeps_the_newest(repository: UserMemoryRepository) -> None:
    await save_in_order(repository, ALICE, "old", "middle", "new")

    assert [r.text for r in await repository.list_memories(ALICE, limit=2)] == ["new", "middle"]


async def test_delete_removes_memory(repository: UserMemoryRepository) -> None:
    record = await repository.save(ALICE, "Temporary")

    await repository.delete(ALICE, record.memory_id)

    assert await repository.list_memories(ALICE) == []
    with pytest.raises(MemoryNotFoundError, match="not found"):
        await repository.delete(ALICE, record.memory_id)


async def test_memories_persist_in_postgres(database_url: str) -> None:
    async with StoreProvider(database_url) as store:
        saved = await UserMemoryRepository(store).save(ALICE, "Stored in Postgres")
    async with StoreProvider(database_url) as store:
        records = await UserMemoryRepository(store).list_memories(ALICE)
        item = await store.aget(memory_namespace(ALICE), saved.memory_id)

    assert [record.text for record in records] == ["Stored in Postgres"]
    assert item is not None
