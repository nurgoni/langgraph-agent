"""Siklus hidup `AsyncPostgresStore`, tempat long-term memory user disimpan (FR-40)."""

from contextlib import AsyncExitStack
from types import TracebackType

from langgraph.store.postgres.aio import AsyncPostgresStore

from agent_service.memory.pool import create_saver_pool, open_saver_pool


class StoreAlreadyOpenError(RuntimeError):
    """`StoreProvider` dibuka lagi sebelum ditutup."""


class StoreProvider:
    """Async context manager yang membuka pool koneksi dan `AsyncPostgresStore`, lalu menutupnya.

    Sama seperti `CheckpointerProvider`: tabel store dibuat oleh migrasi (`upgrade_database`),
    bukan di sini, dan satu instance hanya boleh dibuka satu kali dalam satu waktu. Store dibuat
    tanpa index embedding, jadi pencarian memakai teks (embedding baru setelah F43).

    Contoh di lifespan FastAPI::

        async with StoreProvider(database_url) as store:
            graph = agent.build(model, checkpointer, store)
    """

    def __init__(self, database_url: str) -> None:
        """Inisialisasi provider tanpa membuka koneksi.

        Args:
            database_url: URL Postgres (`DATABASE_URL`).
        """
        self._database_url = database_url
        self._exit_stack: AsyncExitStack | None = None

    async def __aenter__(self) -> AsyncPostgresStore:
        """Buka pool koneksi dan buat store.

        Returns:
            Store yang siap dipakai repository memory dan agent.

        Raises:
            StoreAlreadyOpenError: Jika provider ini masih terbuka.
            DatabaseUnavailableError: Jika Postgres tidak bisa dihubungi.
        """
        if self._exit_stack is not None:
            raise StoreAlreadyOpenError("Store is already open")
        pool = create_saver_pool(self._database_url)
        async with AsyncExitStack() as exit_stack:
            exit_stack.push_async_callback(pool.close)
            await open_saver_pool(pool, self._database_url)
            self._exit_stack = exit_stack.pop_all()
        return AsyncPostgresStore(conn=pool)

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
