"""Environment Alembic untuk tabel aplikasi (`memory/tables.py`).

Modul ini dieksekusi oleh Alembic, bukan di-import, jadi kode di level modul adalah konvensi
Alembic (pengecualian aturan "tanpa side effect saat import"). Folder `migrations/` dikecualikan
dari koleksi doctest pytest.

- Jalur utama: `upgrade_database()` (`run_migrate`) memberikan koneksi lewat
  `config.attributes["connection"]`.
- CLI `uv run alembic revision --autogenerate -m "..."`: tanpa koneksi, engine dibuat dari
  `DATABASE_URL` di `Settings`.
"""

import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from agent_service.memory.tables import METADATA

CONNECTION_ATTRIBUTE = "connection"


def run_with_connection(connection: Connection) -> None:
    """Jalankan migrasi di koneksi yang sudah terbuka."""
    context.configure(connection=connection, target_metadata=METADATA)
    with context.begin_transaction():
        context.run_migrations()


async def run_with_new_engine() -> None:
    """Buat engine dari `Settings`, lalu jalankan migrasi (dipakai CLI `alembic`)."""
    from agent_service.core.settings import Settings
    from agent_service.memory.database import create_database_engine

    engine = create_database_engine(Settings().database_url.get_secret_value())
    try:
        async with engine.begin() as connection:
            await connection.run_sync(run_with_connection)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline (--sql) migrations are not supported")

provided_connection = context.config.attributes.get(CONNECTION_ATTRIBUTE)
if provided_connection is None:
    asyncio.run(run_with_new_engine(), loop_factory=asyncio.SelectorEventLoop)
else:
    run_with_connection(provided_connection)
