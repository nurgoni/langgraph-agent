"""Migrasi skema Postgres: tabel checkpointer dan store LangGraph, lalu tabel aplikasi (Alembic).

Migrasi dijalankan sekali oleh service compose `migrate` (`run_migrate`), bukan di lifespan,
supaya beberapa replika atau worker tidak menjalankannya bersamaan (ADR 0001). Lifespan hanya
memanggil `ensure_database_migrated` agar service gagal cepat jika migrasi belum dijalankan.

Ditulis sebagai function: masing-masing satu aksi tanpa state (AGENTS.md § Class vs Function).
"""

import logging
from pathlib import Path
from typing import Final

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from psycopg.conninfo import make_conninfo
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_service.memory.database import (
    DB_CONNECT_TIMEOUT_SECONDS,
    create_database_engine,
    describe_database,
)

logger = logging.getLogger(__name__)

MIGRATIONS_DIR: Final = Path(__file__).parent / "migrations"
HEAD_REVISION: Final = "head"
# Sama dengan CONNECTION_ATTRIBUTE di migrations/env.py, yang tidak bisa di-import (bukan modul).
CONNECTION_ATTRIBUTE: Final = "connection"
RUN_MIGRATE_HINT: Final = (
    "Run `uv run python -m agent_service.run_migrate` or `docker compose up migrate`."
)


class DatabaseNotMigratedError(RuntimeError):
    """Skema database belum sama dengan migrasi terbaru."""


def alembic_config(connection: Connection | None = None) -> Config:
    """Konfigurasi Alembic tanpa file `alembic.ini`, menunjuk ke folder migrasi di package.

    Args:
        connection: Koneksi sinkron yang dipakai `env.py`. `None` untuk operasi baca skrip.

    >>> alembic_config().get_main_option("script_location") == str(MIGRATIONS_DIR)
    True
    """
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    if connection is not None:
        config.attributes[CONNECTION_ATTRIBUTE] = connection
    return config


def expected_heads() -> set[str]:
    """Revisi terbaru yang ada di folder migrasi.

    >>> expected_heads()
    {'0005'}
    """
    return set(ScriptDirectory.from_config(alembic_config()).get_heads())


async def upgrade_database(database_url: str) -> None:
    """Siapkan tabel checkpointer dan store, lalu jalankan migrasi Alembic sampai `head`.

    Tabel LangGraph disiapkan lebih dulu, sehingga revisi Alembic yang terbaru menandakan seluruh
    migrasi (termasuk checkpointer dan store) sudah selesai. Aman dijalankan berulang.

    Args:
        database_url: URL Postgres (`DATABASE_URL`).
    """
    location = describe_database(database_url)
    logger.info("Migrating database %s", location)
    saver_conninfo = make_conninfo(database_url, connect_timeout=DB_CONNECT_TIMEOUT_SECONDS)
    async with AsyncPostgresSaver.from_conn_string(saver_conninfo) as saver:
        await saver.setup()
    async with AsyncPostgresStore.from_conn_string(saver_conninfo) as store:
        await store.setup()
    engine = create_database_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_upgrade_to_head)
    finally:
        await engine.dispose()
    logger.info("Database %s is at revision %s", location, sorted(expected_heads()))


async def ensure_database_migrated(engine: AsyncEngine) -> None:
    """Pastikan revisi database sama dengan migrasi terbaru.

    Args:
        engine: Engine ke database yang akan dipakai service.

    Raises:
        DatabaseNotMigratedError: Jika migrasi belum (atau belum semua) dijalankan.
    """
    async with engine.connect() as connection:
        current = await connection.run_sync(_current_heads)
    expected = expected_heads()
    if current != expected:
        raise DatabaseNotMigratedError(
            f"Database schema is at {sorted(current) or 'no revision'}, "
            f"expected {sorted(expected)}. {RUN_MIGRATE_HINT}"
        )


def _upgrade_to_head(connection: Connection) -> None:
    """Jalankan `alembic upgrade head` di koneksi sinkron (dari `run_sync`)."""
    command.upgrade(alembic_config(connection), HEAD_REVISION)


def _current_heads(connection: Connection) -> set[str]:
    """Revisi yang tercatat di tabel `alembic_version`."""
    return set(MigrationContext.configure(connection).get_current_heads())
