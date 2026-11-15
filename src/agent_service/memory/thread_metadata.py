"""Penyimpanan judul custom thread di tabel Postgres `thread_metadata` (FR-25).

Metadata checkpoint LangGraph tidak dirancang untuk diubah setelah ditulis, jadi judul custom
disimpan terpisah, di database yang sama dengan checkpointer.
"""

from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_service.memory.tables import thread_metadata_table


class ThreadMetadataRepository:
    """Membaca dan menulis judul custom thread.

    Engine dibuat dan ditutup oleh `DatabaseEngineProvider` di lifespan. Repository hanya
    memakainya, jadi tidak perlu dibuka atau ditutup sendiri.

    Contoh di lifespan::

        async with DatabaseEngineProvider(database_url) as engine:
            titles = ThreadMetadataRepository(engine)
            await titles.set_title("thread-1", "Rencana liburan")
    """

    def __init__(self, engine: AsyncEngine) -> None:
        """Inisialisasi repository.

        Args:
            engine: Engine ke database yang sudah dimigrasi.
        """
        self._engine = engine

    async def set_title(self, thread_id: str, title: str) -> None:
        """Simpan atau ganti judul custom thread."""
        statement = insert(thread_metadata_table).values(thread_id=thread_id, title=title)
        upsert = statement.on_conflict_do_update(
            index_elements=[thread_metadata_table.c.thread_id],
            set_={"title": statement.excluded.title},
        )
        async with self._engine.begin() as connection:
            await connection.execute(upsert)

    async def get_titles(self, thread_ids: Iterable[str]) -> dict[str, str]:
        """Ambil judul custom untuk banyak thread sekaligus.

        Args:
            thread_ids: Thread yang dicari.

        Returns:
            Peta `thread_id → judul`. Thread tanpa judul custom tidak ada di peta.
        """
        ids = list(thread_ids)
        if not ids:
            return {}
        query = select(thread_metadata_table.c.thread_id, thread_metadata_table.c.title).where(
            thread_metadata_table.c.thread_id.in_(ids)
        )
        titles: dict[str, str] = {}
        async with self._engine.connect() as connection:
            result = await connection.execute(query)
            for thread_id, title in result:
                titles[thread_id] = title
        return titles

    async def delete(self, thread_id: str) -> None:
        """Hapus judul custom thread. Tidak error jika thread tidak punya judul custom."""
        statement = delete(thread_metadata_table).where(
            thread_metadata_table.c.thread_id == thread_id
        )
        async with self._engine.begin() as connection:
            await connection.execute(statement)


if __name__ == "__main__":
    import asyncio

    from agent_service.core.constants import DEFAULT_DATABASE_URL
    from agent_service.memory.database import DatabaseEngineProvider

    async def _demo() -> None:
        # Butuh `docker compose up -d postgres` dan `uv run python -m agent_service.run_migrate`.
        async with DatabaseEngineProvider(DEFAULT_DATABASE_URL) as engine:
            titles = ThreadMetadataRepository(engine)
            await titles.set_title("demo", "Rencana liburan")
            print(await titles.get_titles(["demo", "missing"]))
            await titles.delete("demo")

    asyncio.run(_demo(), loop_factory=asyncio.SelectorEventLoop)
