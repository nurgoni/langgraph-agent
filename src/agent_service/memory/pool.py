"""Pool koneksi psycopg untuk komponen LangGraph berbasis Postgres (checkpointer dan store).

`AsyncPostgresSaver` dan `AsyncPostgresStore` menuntut opsi koneksi yang sama, jadi keduanya
membuat pool lewat modul ini. Ditulis sebagai function: masing-masing satu aksi tanpa state.
"""

from typing import Any, Final

from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool, PoolTimeout

from agent_service.memory.database import (
    DB_CONNECT_TIMEOUT_SECONDS,
    START_DATABASE_HINT,
    DatabaseUnavailableError,
    describe_database,
)

POOL_MIN_SIZE: Final = 1
POOL_MAX_SIZE: Final = 10
POOL_OPEN_TIMEOUT_SECONDS: Final = 10.0
# Wajib untuk saver dan store LangGraph: autocommit untuk setiap operasi, tanpa prepared statement
# (aman di belakang pgbouncer), dan baris berupa dict.
SAVER_CONNECTION_KWARGS: Final[dict[str, Any]] = {  # Any: kwargs psycopg.connect
    "autocommit": True,
    "prepare_threshold": 0,
    "row_factory": dict_row,
    "connect_timeout": DB_CONNECT_TIMEOUT_SECONDS,
}

type SaverPool = AsyncConnectionPool[AsyncConnection[DictRow]]


def create_saver_pool(database_url: str) -> SaverPool:
    """Pool yang belum dibuka, dengan opsi koneksi untuk saver/store LangGraph.

    >>> pool = create_saver_pool("postgresql://agent:agent@127.0.0.1:5432/agent_service")
    >>> pool.max_size, pool.closed
    (10, True)
    """
    return AsyncConnectionPool(
        database_url,
        min_size=POOL_MIN_SIZE,
        max_size=POOL_MAX_SIZE,
        kwargs=SAVER_CONNECTION_KWARGS,
        open=False,
    )


async def open_saver_pool(pool: SaverPool, database_url: str) -> None:
    """Buka pool dan tunggu koneksi pertama, supaya startup gagal cepat jika database mati.

    Args:
        pool: Pool dari `create_saver_pool`.
        database_url: URL yang sama, hanya untuk pesan error (password disembunyikan).

    Raises:
        DatabaseUnavailableError: Jika tidak ada koneksi dalam batas waktu.
    """
    try:
        await pool.open(wait=True, timeout=POOL_OPEN_TIMEOUT_SECONDS)
    except PoolTimeout as error:
        location = describe_database(database_url)
        raise DatabaseUnavailableError(
            f"Cannot connect to Postgres at {location}. {START_DATABASE_HINT}"
        ) from error
