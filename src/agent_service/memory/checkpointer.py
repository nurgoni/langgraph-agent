"""Siklus hidup checkpointer Postgres yang dipakai graph LangGraph (ADR 0001)."""

from contextlib import AsyncExitStack
from types import TracebackType

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from agent_service.memory.pool import create_saver_pool, open_saver_pool


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
        pool = create_saver_pool(self._database_url)
        async with AsyncExitStack() as exit_stack:
            exit_stack.push_async_callback(pool.close)
            await open_saver_pool(pool, self._database_url)
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
