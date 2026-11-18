"""Penyimpanan metadata artifact di tabel `artifacts` (FR-46, F35).

Repository ini tidak memeriksa hak akses: setiap pembacaan disaring `owner_id` oleh pemanggil
(`service/artifacts.py`), sehingga artifact milik user lain tidak pernah dikembalikan (NFR-9).
Isi file disimpan terpisah di `ArtifactStore`.
"""

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_service.memory.tables import artifacts_table


@dataclass(frozen=True)
class NewArtifact:
    """Metadata artifact yang akan disimpan (tanpa waktu dibuat)."""

    artifact_id: str
    owner_id: str
    name: str
    mime_type: str
    size_bytes: int
    storage_key: str
    thread_id: str | None = None


@dataclass(frozen=True)
class ArtifactRecord:
    """Satu baris tabel `artifacts`."""

    artifact_id: str
    owner_id: str
    thread_id: str | None
    name: str
    mime_type: str
    size_bytes: int
    storage_key: str
    created_at: datetime


class ArtifactRepository:
    """Membuat, membaca, menautkan ke thread, dan menghapus metadata artifact.

    Engine dimiliki `DatabaseEngineProvider` di lifespan.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        """Inisialisasi repository.

        Args:
            engine: Engine ke database yang sudah dimigrasi.
        """
        self._engine = engine

    async def add(self, artifact: NewArtifact) -> ArtifactRecord:
        """Simpan metadata artifact baru dan kembalikan barisnya."""
        query = insert(artifacts_table).values(**asdict(artifact)).returning(artifacts_table)
        async with self._engine.begin() as connection:
            row = (await connection.execute(query)).one()
        return ArtifactRecord(**row._asdict())

    async def get_owned(self, artifact_ids: Sequence[str], owner_id: str) -> list[ArtifactRecord]:
        """Artifact milik `owner_id` dari daftar ID. ID milik user lain atau tidak ada dilewati.

        Args:
            artifact_ids: ID artifact yang dicari. ID yang bukan UUID valid dilewati.
            owner_id: Pemilik artifact.

        Returns:
            Artifact yang ditemukan, tanpa urutan tertentu.
        """
        valid_ids = [artifact_id for artifact_id in artifact_ids if _is_uuid(artifact_id)]
        if not valid_ids:
            return []
        table = artifacts_table
        query = select(table).where(
            table.c.artifact_id.in_(valid_ids), table.c.owner_id == owner_id
        )
        async with self._engine.connect() as connection:
            result = await connection.execute(query)
            return [ArtifactRecord(**row._asdict()) for row in result]

    async def link_to_thread(self, artifact_ids: Sequence[str], thread_id: str) -> None:
        """Tautkan artifact yang belum punya thread ke `thread_id`.

        Artifact yang sudah tertaut tidak diubah, jadi pemanggilan ulang untuk thread yang sama
        aman.
        """
        if not artifact_ids:
            return
        table = artifacts_table
        query = (
            update(table)
            .where(table.c.artifact_id.in_(list(artifact_ids)), table.c.thread_id.is_(None))
            .values(thread_id=thread_id)
        )
        async with self._engine.begin() as connection:
            await connection.execute(query)

    async def delete(self, artifact_id: str) -> None:
        """Hapus metadata satu artifact. ID yang tidak ada diabaikan."""
        table = artifacts_table
        async with self._engine.begin() as connection:
            await connection.execute(delete(table).where(table.c.artifact_id == artifact_id))

    async def delete_thread(self, thread_id: str) -> list[ArtifactRecord]:
        """Hapus semua metadata artifact milik satu thread.

        Returns:
            Baris yang dihapus, supaya file di `ArtifactStore` ikut dihapus.
        """
        table = artifacts_table
        query = delete(table).where(table.c.thread_id == thread_id).returning(table)
        async with self._engine.begin() as connection:
            result = await connection.execute(query)
            return [ArtifactRecord(**row._asdict()) for row in result]


def _is_uuid(value: str) -> bool:
    """Cek format UUID, supaya ID dari request tidak membuat Postgres menolak query.

    >>> _is_uuid("0b9e3c1e-5f7a-4c2b-9d61-3f0a2b7c8d90"), _is_uuid("../etc")
    (True, False)
    """
    try:
        UUID(value)
    except ValueError:
        return False
    return True


if __name__ == "__main__":
    import asyncio
    import uuid

    from agent_service.core.constants import DEFAULT_DATABASE_URL
    from agent_service.memory.database import DatabaseEngineProvider

    async def _demo() -> None:
        # Butuh `docker compose up -d postgres` dan `uv run python -m agent_service.run_migrate`.
        artifact_id = str(uuid.uuid4())
        artifact = NewArtifact(artifact_id, "demo", "notes.txt", "text/plain", 5, artifact_id)
        async with DatabaseEngineProvider(DEFAULT_DATABASE_URL) as engine:
            repository = ArtifactRepository(engine)
            print(await repository.add(artifact))
            await repository.delete(artifact_id)

    asyncio.run(_demo())
