"""Siklus hidup checkpointer SQLite yang dipakai graph LangGraph."""

import asyncio
from contextlib import AsyncExitStack
from pathlib import Path
from types import TracebackType

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


class CheckpointerAlreadyOpenError(RuntimeError):
    """`CheckpointerProvider` dibuka lagi sebelum ditutup."""


class CheckpointerProvider:
    """Async context manager yang membuka `AsyncSqliteSaver` dan menutupnya saat keluar.

    Folder induk file database dibuat jika belum ada, dan tabel checkpoint dibuat sekali saat
    masuk, sehingga request pertama tidak menanggung biaya setup. Satu instance hanya boleh
    dibuka satu kali dalam satu waktu, tapi boleh dibuka lagi setelah ditutup.

    Contoh di lifespan FastAPI::

        async with CheckpointerProvider(settings.sqlite_db_path) as checkpointer:
            graph = builder.compile(checkpointer=checkpointer)
    """

    def __init__(self, db_path: Path) -> None:
        """Inisialisasi provider tanpa membuka koneksi.

        Args:
            db_path: Lokasi file database SQLite (`SQLITE_DB_PATH`).
        """
        self._db_path = db_path
        self._exit_stack: AsyncExitStack | None = None

    async def __aenter__(self) -> AsyncSqliteSaver:
        """Buka koneksi dan siapkan tabel checkpoint.

        Returns:
            Saver yang siap diberikan ke `graph.compile(checkpointer=...)`.

        Raises:
            CheckpointerAlreadyOpenError: Jika provider ini masih terbuka.
        """
        if self._exit_stack is not None:
            raise CheckpointerAlreadyOpenError(f"Checkpointer {self._db_path} is already open")
        await asyncio.to_thread(self._db_path.parent.mkdir, parents=True, exist_ok=True)
        async with AsyncExitStack() as exit_stack:
            saver = await exit_stack.enter_async_context(
                AsyncSqliteSaver.from_conn_string(str(self._db_path))
            )
            await saver.setup()
            # pop_all memindahkan cleanup ke __aexit__. Jika setup gagal, koneksi langsung ditutup.
            self._exit_stack = exit_stack.pop_all()
        return saver

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Tutup koneksi database. Aman dipanggil walau provider belum dibuka."""
        exit_stack = self._exit_stack
        self._exit_stack = None
        if exit_stack is not None:
            await exit_stack.aclose()


if __name__ == "__main__":
    import tempfile

    from langgraph.checkpoint.base import empty_checkpoint

    async def _demo(db_path: Path) -> None:
        config = {"configurable": {"thread_id": "demo", "checkpoint_ns": ""}}
        async with CheckpointerProvider(db_path) as saver:
            await saver.aput(config, empty_checkpoint(), {}, {})
        async with CheckpointerProvider(db_path) as saver:
            print(await saver.aget_tuple(config))

    with tempfile.TemporaryDirectory() as temp_dir:
        asyncio.run(_demo(Path(temp_dir) / "demo.db"))
