from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_service.memory.checkpointer import CheckpointerProvider
from agent_service.memory.database import DatabaseEngineProvider
from agent_service.memory.thread_metadata import ThreadMetadataRepository


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    async with DatabaseEngineProvider(database_url) as database_engine:
        yield database_engine


@pytest.fixture
def titles(engine: AsyncEngine) -> ThreadMetadataRepository:
    return ThreadMetadataRepository(engine)


async def test_set_then_get_title(titles: ThreadMetadataRepository) -> None:
    await titles.set_title("t1", "Rencana liburan")

    assert await titles.get_titles(["t1", "t2"]) == {"t1": "Rencana liburan"}


async def test_set_title_replaces_existing(titles: ThreadMetadataRepository) -> None:
    await titles.set_title("t1", "Lama")
    await titles.set_title("t1", "Baru")

    assert await titles.get_titles(["t1"]) == {"t1": "Baru"}


async def test_get_titles_with_no_ids_is_empty(titles: ThreadMetadataRepository) -> None:
    assert await titles.get_titles([]) == {}


async def test_delete_removes_title(titles: ThreadMetadataRepository) -> None:
    await titles.set_title("t1", "Judul")

    await titles.delete("t1")
    await titles.delete("never-set")

    assert await titles.get_titles(["t1"]) == {}


async def test_titles_persist_across_engines(database_url: str) -> None:
    async with DatabaseEngineProvider(database_url) as first_engine:
        await ThreadMetadataRepository(first_engine).set_title("t1", "Tetap ada")
    async with DatabaseEngineProvider(database_url) as second_engine:
        titles = await ThreadMetadataRepository(second_engine).get_titles(["t1"])

    assert titles == {"t1": "Tetap ada"}


async def test_shares_database_with_checkpointer(
    database_url: str, titles: ThreadMetadataRepository
) -> None:
    async with CheckpointerProvider(database_url) as saver:
        await titles.set_title("t1", "Berdampingan")

        assert await saver.aget_tuple({"configurable": {"thread_id": "t1"}}) is None
    assert await titles.get_titles(["t1"]) == {"t1": "Berdampingan"}
