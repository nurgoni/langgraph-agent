"""Penyimpanan judul custom thread di tabel `thread_metadata` (FR-25).

Metadata checkpoint LangGraph tidak dirancang untuk diubah setelah ditulis, jadi judul custom
disimpan terpisah, di file SQLite yang sama dengan checkpointer, lewat koneksi sendiri.
"""

import asyncio
from collections.abc import Iterable
from pathlib import Path
from types import TracebackType
from typing import Final, Self

import aiosqlite

CREATE_TABLE_SQL: Final = """
CREATE TABLE IF NOT EXISTS thread_metadata (
    thread_id TEXT PRIMARY KEY,
    title TEXT NOT NULL
)
"""
UPSERT_TITLE_SQL: Final = """
INSERT INTO thread_metadata (thread_id, title) VALUES (?, ?)
ON CONFLICT(thread_id) DO UPDATE SET title = excluded.title
"""
SELECT_TITLES_SQL: Final = "SELECT thread_id, title FROM thread_metadata WHERE thread_id IN ({})"
DELETE_SQL: Final = "DELETE FROM thread_metadata WHERE thread_id = ?"
SQL_PLACEHOLDER: Final = "?"


class ThreadMetadataNotOpenError(RuntimeError):
    """Repository dipakai sebelum dibuka dengan `async with`, atau dibuka dua kali."""


class ThreadMetadataRepository:
    """Async context manager untuk membaca dan menulis judul custom thread.

    Satu koneksi dibuka saat masuk dan ditutup saat keluar. Tabel dibuat jika belum ada.

    Contoh di lifespan::

        async with ThreadMetadataRepository(settings.sqlite_db_path) as titles:
            await titles.set_title("thread-1", "Rencana liburan")
    """

    def __init__(self, db_path: Path) -> None:
        """Inisialisasi repository tanpa membuka koneksi.

        Args:
            db_path: File SQLite yang sama dengan `SQLITE_DB_PATH`.
        """
        self._db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    async def __aenter__(self) -> Self:
        """Buka koneksi dan pastikan tabel ada.

        Raises:
            ThreadMetadataNotOpenError: Jika repository ini sudah terbuka.
        """
        if self._connection is not None:
            raise ThreadMetadataNotOpenError(f"Thread metadata {self._db_path} is already open")
        await asyncio.to_thread(self._db_path.parent.mkdir, parents=True, exist_ok=True)
        connection = await aiosqlite.connect(self._db_path)
        await connection.execute(CREATE_TABLE_SQL)
        await connection.commit()
        self._connection = connection
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Tutup koneksi. Aman dipanggil walau repository belum dibuka."""
        connection = self._connection
        self._connection = None
        if connection is not None:
            await connection.close()

    async def set_title(self, thread_id: str, title: str) -> None:
        """Simpan atau ganti judul custom thread."""
        connection = self._require_connection()
        await connection.execute(UPSERT_TITLE_SQL, (thread_id, title))
        await connection.commit()

    async def get_titles(self, thread_ids: Iterable[str]) -> dict[str, str]:
        """Ambil judul custom untuk banyak thread sekaligus.

        Args:
            thread_ids: Thread yang dicari.

        Returns:
            Peta `thread_id → judul`. Thread tanpa judul custom tidak ada di peta.
        """
        connection = self._require_connection()
        ids = list(thread_ids)
        if not ids:
            return {}
        placeholders = ", ".join([SQL_PLACEHOLDER] * len(ids))
        titles: dict[str, str] = {}
        async with connection.execute(SELECT_TITLES_SQL.format(placeholders), ids) as cursor:
            async for thread_id, title in cursor:
                titles[thread_id] = title
        return titles

    async def delete(self, thread_id: str) -> None:
        """Hapus judul custom thread. Tidak error jika thread tidak punya judul custom."""
        connection = self._require_connection()
        await connection.execute(DELETE_SQL, (thread_id,))
        await connection.commit()

    def _require_connection(self) -> aiosqlite.Connection:
        """Koneksi aktif.

        Raises:
            ThreadMetadataNotOpenError: Jika repository belum dibuka.
        """
        if self._connection is None:
            raise ThreadMetadataNotOpenError("Thread metadata repository is not open")
        return self._connection


if __name__ == "__main__":
    import tempfile

    async def _demo(db_path: Path) -> None:
        async with ThreadMetadataRepository(db_path) as titles:
            await titles.set_title("t1", "Rencana liburan")
            print(await titles.get_titles(["t1", "t2"]))

    with tempfile.TemporaryDirectory() as temp_dir:
        asyncio.run(_demo(Path(temp_dir) / "demo.db"))
