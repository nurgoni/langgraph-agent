from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import empty_checkpoint

from agent_service.memory.checkpointer import (
    CheckpointerAlreadyOpenError,
    CheckpointerProvider,
)

THREAD_ID = "thread-1"


def thread_config(thread_id: str = THREAD_ID) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "checkpoints.db"


async def test_checkpoint_persists_across_provider_instances(db_path: Path) -> None:
    checkpoint = empty_checkpoint()

    async with CheckpointerProvider(db_path) as saver:
        await saver.aput(thread_config(), checkpoint, {}, {})
    async with CheckpointerProvider(db_path) as saver:
        stored = await saver.aget_tuple(thread_config())

    assert stored is not None
    assert stored.checkpoint["id"] == checkpoint["id"]


async def test_unknown_thread_has_no_checkpoint(db_path: Path) -> None:
    async with CheckpointerProvider(db_path) as saver:
        assert await saver.aget_tuple(thread_config("missing")) is None


async def test_tables_are_ready_on_enter(db_path: Path) -> None:
    async with CheckpointerProvider(db_path) as saver:
        assert saver.is_setup
    assert db_path.exists()


async def test_missing_parent_directory_is_created(tmp_path: Path) -> None:
    nested_path = tmp_path / "data" / "nested" / "checkpoints.db"

    async with CheckpointerProvider(nested_path):
        pass

    assert nested_path.exists()


async def test_entering_twice_while_open_is_rejected(db_path: Path) -> None:
    provider = CheckpointerProvider(db_path)

    async with provider:
        with pytest.raises(CheckpointerAlreadyOpenError):
            await provider.__aenter__()


async def test_provider_can_reopen_after_close(db_path: Path) -> None:
    provider = CheckpointerProvider(db_path)

    async with provider as first_saver:
        await first_saver.aput(thread_config(), empty_checkpoint(), {}, {})
    async with provider as second_saver:
        assert await second_saver.aget_tuple(thread_config()) is not None


async def test_connection_is_closed_on_exit(db_path: Path) -> None:
    async with CheckpointerProvider(db_path) as saver:
        pass

    with pytest.raises(ValueError, match="no active connection"):
        await saver.conn.execute("SELECT 1")


async def test_exit_without_enter_is_noop(db_path: Path) -> None:
    await CheckpointerProvider(db_path).__aexit__(None, None, None)
