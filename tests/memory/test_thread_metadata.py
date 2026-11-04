from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from agent_service.memory.checkpointer import CheckpointerProvider
from agent_service.memory.thread_metadata import (
    ThreadMetadataNotOpenError,
    ThreadMetadataRepository,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "checkpoints.db"


@pytest.fixture
async def titles(db_path: Path) -> AsyncIterator[ThreadMetadataRepository]:
    async with ThreadMetadataRepository(db_path) as repository:
        yield repository


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


async def test_titles_persist_across_connections(db_path: Path) -> None:
    async with ThreadMetadataRepository(db_path) as first:
        await first.set_title("t1", "Tetap ada")
    async with ThreadMetadataRepository(db_path) as second:
        assert await second.get_titles(["t1"]) == {"t1": "Tetap ada"}


async def test_shares_database_file_with_checkpointer(db_path: Path) -> None:
    async with (
        CheckpointerProvider(db_path) as saver,
        ThreadMetadataRepository(db_path) as titles,
    ):
        await titles.set_title("t1", "Berdampingan")
        assert await saver.aget_tuple({"configurable": {"thread_id": "t1"}}) is None
        assert await titles.get_titles(["t1"]) == {"t1": "Berdampingan"}


async def test_use_before_open_is_rejected(db_path: Path) -> None:
    with pytest.raises(ThreadMetadataNotOpenError):
        await ThreadMetadataRepository(db_path).get_titles(["t1"])


async def test_entering_twice_is_rejected(titles: ThreadMetadataRepository) -> None:
    with pytest.raises(ThreadMetadataNotOpenError):
        await titles.__aenter__()


async def test_exit_without_enter_is_noop(db_path: Path) -> None:
    await ThreadMetadataRepository(db_path).__aexit__(None, None, None)
