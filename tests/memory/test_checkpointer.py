import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import empty_checkpoint

from agent_service.memory.checkpointer import (
    SAVER_CONNECTION_KWARGS,
    CheckpointerAlreadyOpenError,
    CheckpointerProvider,
)
from agent_service.memory.database import DatabaseUnavailableError

THREAD_ID = "thread-1"
# Port 1 di loopback: koneksi ditolak. Di Windows penolakan baru terlihat setelah timeout.
UNREACHABLE_URL = "postgresql://agent:agent@127.0.0.1:1/agent_service"


def thread_config(thread_id: str = THREAD_ID) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}


async def test_checkpoint_persists_across_provider_instances(database_url: str) -> None:
    checkpoint = empty_checkpoint()

    async with CheckpointerProvider(database_url) as saver:
        await saver.aput(thread_config(), checkpoint, {}, {})
    async with CheckpointerProvider(database_url) as saver:
        stored = await saver.aget_tuple(thread_config())

    assert stored is not None
    assert stored.checkpoint["id"] == checkpoint["id"]


async def test_unknown_thread_has_no_checkpoint(database_url: str) -> None:
    async with CheckpointerProvider(database_url) as saver:
        assert await saver.aget_tuple(thread_config("missing")) is None


async def test_entering_twice_while_open_is_rejected(database_url: str) -> None:
    provider = CheckpointerProvider(database_url)

    async with provider:
        with pytest.raises(CheckpointerAlreadyOpenError):
            await provider.__aenter__()


async def test_provider_can_reopen_after_close(database_url: str) -> None:
    provider = CheckpointerProvider(database_url)

    async with provider as first_saver:
        await first_saver.aput(thread_config(), empty_checkpoint(), {}, {})
    async with provider as second_saver:
        assert await second_saver.aget_tuple(thread_config()) is not None


async def test_pool_is_closed_on_exit(database_url: str) -> None:
    async with CheckpointerProvider(database_url) as saver:
        pass

    with pytest.raises(Exception, match="closed"):
        await saver.aget_tuple(thread_config())


async def test_unreachable_database_fails_fast_with_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    module = "agent_service.memory.checkpointer"
    monkeypatch.setattr(f"{module}.POOL_OPEN_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setitem(SAVER_CONNECTION_KWARGS, "connect_timeout", 1)

    with pytest.raises(DatabaseUnavailableError, match="docker compose up -d postgres"):
        async with CheckpointerProvider(UNREACHABLE_URL):
            pass


async def test_exit_without_enter_is_noop(database_url: str) -> None:
    await CheckpointerProvider(database_url).__aexit__(None, None, None)
