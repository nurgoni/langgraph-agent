"""`PostgresWorkspace`: workspace per thread di tabel `workspace_files` (FR-47, F36).

Implementasi protocol `Workspace` dari `files/workspace.py`. Repository ini tidak memeriksa hak
akses: thread sudah diperiksa pemiliknya oleh service sebelum run dimulai, dan tool hanya
memakai `thread_id` dari config run.
"""

import logging
from typing import Final

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_service.files.workspace import (
    WorkspaceFile,
    WorkspaceFileNotFoundError,
    WorkspaceFileTooLargeError,
)
from agent_service.memory.tables import workspace_files_table

logger = logging.getLogger(__name__)

# Urutan byte, sama dengan `InMemoryWorkspace`; collation locale mengabaikan tanda baca.
BYTE_ORDER_COLLATION: Final = "C"


class PostgresWorkspace:
    """File workspace semua thread, disimpan di Postgres.

    Engine dimiliki `DatabaseEngineProvider` di lifespan.
    """

    def __init__(self, engine: AsyncEngine, max_file_bytes: int) -> None:
        """Inisialisasi workspace.

        Args:
            engine: Engine ke database yang sudah dimigrasi.
            max_file_bytes: Batas ukuran satu file (sama dengan `ARTIFACT_MAX_BYTES`, supaya file
                workspace selalu bisa dibagikan sebagai artifact).
        """
        self._engine = engine
        self._max_file_bytes = max_file_bytes

    async def read(self, thread_id: str, path: str) -> bytes:
        """Isi satu file. Lihat `Workspace.read`."""
        table = workspace_files_table
        query = select(table.c.content).where(table.c.thread_id == thread_id, table.c.path == path)
        async with self._engine.connect() as connection:
            content = (await connection.execute(query)).scalar_one_or_none()
        if content is None:
            raise WorkspaceFileNotFoundError(path)
        return bytes(content)

    async def write(self, thread_id: str, path: str, content: bytes) -> None:
        """Buat atau timpa satu file. Lihat `Workspace.write`."""
        if len(content) > self._max_file_bytes:
            raise WorkspaceFileTooLargeError(path, self._max_file_bytes)
        table = workspace_files_table
        values = {
            "thread_id": thread_id,
            "path": path,
            "content": content,
            "size_bytes": len(content),
        }
        query = insert(table).values(**values)
        query = query.on_conflict_do_update(
            index_elements=[table.c.thread_id, table.c.path],
            set_={"content": content, "size_bytes": len(content), "updated_at": func.now()},
        )
        async with self._engine.begin() as connection:
            await connection.execute(query)

    async def list_files(self, thread_id: str, prefix: str = "") -> list[WorkspaceFile]:
        """File di bawah `prefix`, urut path. Lihat `Workspace.list_files`."""
        table = workspace_files_table
        query = (
            select(table.c.path, table.c.size_bytes, table.c.updated_at)
            .where(table.c.thread_id == thread_id, table.c.path.startswith(prefix, autoescape=True))
            .order_by(table.c.path.collate(BYTE_ORDER_COLLATION))
        )
        async with self._engine.connect() as connection:
            result = await connection.execute(query)
            return [WorkspaceFile(row.path, row.size_bytes, row.updated_at) for row in result]

    async def delete_thread_data(self, thread_id: str) -> None:
        """Hapus seluruh workspace thread. Lihat `Workspace.delete_thread_data`."""
        table = workspace_files_table
        query = delete(table).where(table.c.thread_id == thread_id)
        async with self._engine.begin() as connection:
            result = await connection.execute(query)
        if result.rowcount:
            logger.info("Deleted %d workspace files of thread %s", result.rowcount, thread_id)


if __name__ == "__main__":
    import asyncio

    from agent_service.core.constants import DEFAULT_ARTIFACT_MAX_BYTES, DEFAULT_DATABASE_URL
    from agent_service.memory.database import DatabaseEngineProvider

    async def _demo() -> None:
        # Butuh `docker compose up -d postgres` dan `uv run python -m agent_service.run_migrate`.
        async with DatabaseEngineProvider(DEFAULT_DATABASE_URL) as engine:
            workspace = PostgresWorkspace(engine, DEFAULT_ARTIFACT_MAX_BYTES)
            await workspace.write("demo-thread", "notes/todo.md", b"- buy milk")
            print(await workspace.list_files("demo-thread"))
            await workspace.delete_thread_data("demo-thread")

    asyncio.run(_demo())
