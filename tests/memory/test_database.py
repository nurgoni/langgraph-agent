import pytest
from sqlalchemy import text

from agent_service.memory.database import (
    DatabaseAlreadyOpenError,
    DatabaseEngineProvider,
    DatabaseUnavailableError,
)

# Port 1 di loopback: koneksi ditolak. Di Windows penolakan baru terlihat setelah timeout.
UNREACHABLE_URL = "postgresql://agent:secret@127.0.0.1:1/agent_service"
FAST_TIMEOUT_SECONDS = 1


async def test_engine_runs_queries(database_url: str) -> None:
    async with DatabaseEngineProvider(database_url) as engine, engine.connect() as connection:
        result = await connection.execute(text("SELECT 1"))

        assert result.scalar_one() == 1


async def test_unreachable_database_fails_fast_without_leaking_password() -> None:
    with pytest.raises(DatabaseUnavailableError) as error_info:
        async with DatabaseEngineProvider(UNREACHABLE_URL, connect_timeout=FAST_TIMEOUT_SECONDS):
            pass

    message = str(error_info.value)
    assert "127.0.0.1:1/agent_service" in message
    assert "docker compose up -d postgres" in message
    assert "secret" not in message


async def test_entering_twice_while_open_is_rejected(database_url: str) -> None:
    provider = DatabaseEngineProvider(database_url)

    async with provider:
        with pytest.raises(DatabaseAlreadyOpenError):
            await provider.__aenter__()


async def test_exit_without_enter_is_noop(database_url: str) -> None:
    await DatabaseEngineProvider(database_url).__aexit__(None, None, None)
