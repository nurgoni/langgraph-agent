import psycopg
import pytest

from agent_service.memory.database import DatabaseEngineProvider
from agent_service.memory.migrator import (
    DatabaseNotMigratedError,
    ensure_database_migrated,
    expected_heads,
    upgrade_database,
)

STALE_REVISION = "stale"


def table_names(database_url: str) -> set[str]:
    with psycopg.connect(database_url) as connection:
        rows = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
    return {row[0] for row in rows}


def set_revision(database_url: str, revision: str) -> None:
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute("UPDATE alembic_version SET version_num = %s", (revision,))


def test_migrated_database_has_app_and_checkpoint_tables(database_url: str) -> None:
    tables = table_names(database_url)

    assert {"thread_metadata", "alembic_version", "checkpoints", "checkpoint_writes"} <= tables


async def test_upgrade_is_idempotent(database_url: str) -> None:
    await upgrade_database(database_url)

    async with DatabaseEngineProvider(database_url) as engine:
        await ensure_database_migrated(engine)


async def test_unmigrated_database_is_rejected_with_hint(database_url: str) -> None:
    set_revision(database_url, STALE_REVISION)
    try:
        async with DatabaseEngineProvider(database_url) as engine:
            with pytest.raises(DatabaseNotMigratedError, match="run_migrate"):
                await ensure_database_migrated(engine)
    finally:
        [head] = expected_heads()
        set_revision(database_url, head)
