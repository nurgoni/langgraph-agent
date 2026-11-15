"""Siklus hidup checkpointer Postgres yang dipakai graph LangGraph (ADR 0001)."""

from contextlib import AsyncExitStack
from types import TracebackType
from typing import Any, Final

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
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
# Wajib untuk AsyncPostgresSaver: autocommit untuk setiap operasi, tanpa prepared statement
# (aman di belakang pgbouncer), dan baris berupa dict.
SAVER_CONNECTION_KWARGS: Final[dict[str, Any]] = {  # Any: kwargs psycopg.connect
    "autocommit": True,
    "prepare_threshold": 0,
    "row_factory": dict_row,
    "connect_timeout": DB_CONNECT_TIMEOUT_SECONDS,
}

type SaverPool = AsyncConnectionPool[AsyncConnection[DictRow]]


class CheckpointerAlreadyOpenError(RuntimeError):
    """`CheckpointerProvider` dibuka lagi sebelum ditutup."""


class CheckpointerProvider:
    """Async context manager yang membuka pool koneksi dan `AsyncPostgresSaver`, lalu menutupnya.

    Tabel checkpoint tidak dibuat di sini, melainkan oleh migrasi (`upgrade_database`). Satu
    instance hanya boleh dibuka satu kali dalam satu waktu, tapi boleh dibuka lagi setelah ditutup.

    Contoh di lifespan FastAPI::

        async with CheckpointerProvider(database_url) as checkpointer:
            graph = builder.compile(checkpointer=checkpointer)
    """

    def __init__(self, database_url: str) -> None:
        """Inisialisasi provider tanpa membuka koneksi.

        Args:
            database_url: URL Postgres (`DATABASE_URL`).
        """
        self._database_url = database_url
        self._exit_stack: AsyncExitStack | None = None

    async def __aenter__(self) -> AsyncPostgresSaver:
        """Buka pool koneksi dan buat saver.

        Returns:
            Saver yang siap diberikan ke `graph.compile(checkpointer=...)`.

        Raises:
            CheckpointerAlreadyOpenError: Jika provider ini masih terbuka.
            DatabaseUnavailableError: Jika Postgres tidak bisa dihubungi.
        """
        if self._exit_stack is not None:
            raise CheckpointerAlreadyOpenError("Checkpointer is already open")
        pool: SaverPool = AsyncConnectionPool(
            self._database_url,
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
            kwargs=SAVER_CONNECTION_KWARGS,
            open=False,
        )
        async with AsyncExitStack() as exit_stack:
            exit_stack.push_async_callback(pool.close)
            await self._open_pool(pool)
            # pop_all memindahkan cleanup ke __aexit__. Jika pool gagal dibuka, langsung ditutup.
            self._exit_stack = exit_stack.pop_all()
        return AsyncPostgresSaver(conn=pool)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Tutup pool koneksi. Aman dipanggil walau provider belum dibuka."""
        exit_stack = self._exit_stack
        self._exit_stack = None
        if exit_stack is not None:
            await exit_stack.aclose()

    async def _open_pool(self, pool: SaverPool) -> None:
        """Buka pool dan tunggu koneksi pertama, supaya startup gagal cepat jika database mati.

        Raises:
            DatabaseUnavailableError: Jika tidak ada koneksi dalam batas waktu.
        """
        try:
            await pool.open(wait=True, timeout=POOL_OPEN_TIMEOUT_SECONDS)
        except PoolTimeout as error:
            location = describe_database(self._database_url)
            raise DatabaseUnavailableError(
                f"Cannot connect to Postgres at {location}. {START_DATABASE_HINT}"
            ) from error
