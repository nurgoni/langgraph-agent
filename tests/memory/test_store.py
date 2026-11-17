import pytest

from agent_service.memory.database import DatabaseUnavailableError
from agent_service.memory.pool import SAVER_CONNECTION_KWARGS
from agent_service.memory.store import StoreAlreadyOpenError, StoreProvider

NAMESPACE = ("users", "user-1", "memories")
# Port 1 di loopback: koneksi ditolak. Di Windows penolakan baru terlihat setelah timeout.
UNREACHABLE_URL = "postgresql://agent:agent@127.0.0.1:1/agent_service"


async def test_items_persist_across_provider_instances(database_url: str) -> None:
    async with StoreProvider(database_url) as store:
        await store.aput(NAMESPACE, "k1", {"text": "hello"})
    async with StoreProvider(database_url) as store:
        item = await store.aget(NAMESPACE, "k1")

    assert item is not None
    assert item.value == {"text": "hello"}


async def test_entering_twice_while_open_is_rejected(database_url: str) -> None:
    provider = StoreProvider(database_url)

    async with provider:
        with pytest.raises(StoreAlreadyOpenError):
            await provider.__aenter__()


async def test_provider_can_reopen_after_close(database_url: str) -> None:
    provider = StoreProvider(database_url)

    async with provider as first:
        await first.aput(NAMESPACE, "k1", {"text": "hello"})
    async with provider as second:
        assert await second.aget(NAMESPACE, "k1") is not None


async def test_unreachable_database_fails_fast_with_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agent_service.memory.pool.POOL_OPEN_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setitem(SAVER_CONNECTION_KWARGS, "connect_timeout", 1)

    with pytest.raises(DatabaseUnavailableError, match="docker compose up -d postgres"):
        async with StoreProvider(UNREACHABLE_URL):
            pass


async def test_exit_without_enter_is_noop(database_url: str) -> None:
    await StoreProvider(database_url).__aexit__(None, None, None)
