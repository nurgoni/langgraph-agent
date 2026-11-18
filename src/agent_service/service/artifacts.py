"""Aturan artifact (FR-46, keputusan user F35): kepemilikan, lampiran pesan, dan penghapusan.

Sejak F36, lampiran juga disalin ke workspace thread (`uploads/<nama>`) supaya agent bisa
membacanya, dan file workspace bisa diterbitkan kembali sebagai artifact (`share_file`).

Artifact milik user lain diperlakukan sama dengan artifact yang tidak ada (404, NFR-9). Artifact
yang dilampirkan ke pesan tertaut ke thread itu, dan ikut terhapus saat thread dihapus.
"""

import logging
from collections.abc import AsyncIterable, AsyncIterator, Sequence
from pathlib import PurePosixPath
from typing import Final
from uuid import uuid4

from agent_service.files.artifacts import ArtifactStore, resolve_mime_type, sanitize_filename
from agent_service.files.workspace import Workspace, unique_path
from agent_service.harness.runtime import HarnessContext
from agent_service.memory.artifacts import ArtifactRecord, ArtifactRepository, NewArtifact
from agent_service.schema.artifacts import ArtifactRef

UPLOADS_FOLDER: Final = "uploads"
# Penanda nama saat path upload sudah dipakai: awal ID artifact cukup untuk membedakan file.
UPLOAD_MARKER_LENGTH: Final = 8

logger = logging.getLogger(__name__)


class ArtifactNotFoundError(LookupError):
    """Artifact tidak ada, atau milik user lain."""

    def __init__(self, artifact_id: str) -> None:
        """Inisialisasi error dengan pesan yang tidak membocorkan pemilik artifact."""
        super().__init__(f"Artifact {artifact_id!r} not found")


class ArtifactThreadConflictError(ValueError):
    """Artifact sudah dilampirkan di thread lain, jadi tidak bisa dilampirkan lagi."""

    def __init__(self, artifact_id: str) -> None:
        """Inisialisasi error untuk artifact yang dimaksud."""
        super().__init__(f"Artifact {artifact_id!r} is already attached to another conversation")


class ArtifactService:
    """Upload, unduh, lampirkan, dan hapus artifact milik user.

    Class karena memegang dependency yang sama untuk semua operasi (repository, store, batas
    ukuran, workspace). Dibuat sekali di lifespan, dipakai `ThreadRepository` untuk membersihkan
    artifact thread yang dihapus, dan menjadi `ArtifactPublisher` untuk tool `share_file`.
    """

    def __init__(
        self,
        repository: ArtifactRepository,
        store: ArtifactStore,
        max_bytes: int,
        workspace: Workspace,
    ) -> None:
        """Inisialisasi service.

        Args:
            repository: Metadata artifact di Postgres.
            store: Tempat isi file disimpan.
            max_bytes: Batas ukuran satu artifact (`ARTIFACT_MAX_BYTES`).
            workspace: Workspace thread, tujuan salinan lampiran (F36).
        """
        self._repository = repository
        self._store = store
        self._max_bytes = max_bytes
        self._workspace = workspace

    def run_context(self) -> HarnessContext:
        """Runtime context tool harness untuk run agent (workspace + penerbit artifact)."""
        return HarnessContext(workspace=self._workspace, artifacts=self)

    @property
    def max_bytes(self) -> int:
        """Batas ukuran satu artifact, dalam byte."""
        return self._max_bytes

    async def upload(
        self,
        owner_id: str,
        filename: str | None,
        content_type: str | None,
        chunks: AsyncIterable[bytes],
    ) -> ArtifactRecord:
        """Simpan file baru milik `owner_id`, belum tertaut ke thread mana pun.

        Args:
            owner_id: Pemilik artifact, dari access token.
            filename: Nama file dari client. Disanitasi sebelum disimpan.
            content_type: Tipe dari client. Ditebak dari ekstensi jika kosong atau tidak valid.
            chunks: Isi file per potongan.

        Returns:
            Metadata artifact yang tersimpan.

        Raises:
            ArtifactTooLargeError: Jika isi melebihi `max_bytes` (413).
        """
        return await self._store_new(owner_id, filename, content_type, chunks, thread_id=None)

    async def publish(
        self, owner_id: str, thread_id: str, filename: str, content: bytes
    ) -> ArtifactRecord:
        """Terbitkan isi file workspace sebagai artifact thread (tool `share_file`, F36).

        Raises:
            ArtifactTooLargeError: Jika isi melebihi `max_bytes`.
        """
        return await self._store_new(owner_id, filename, None, _single_chunk(content), thread_id)

    async def _store_new(
        self,
        owner_id: str,
        filename: str | None,
        content_type: str | None,
        chunks: AsyncIterable[bytes],
        thread_id: str | None,
    ) -> ArtifactRecord:
        """Simpan isi lalu metadata artifact baru. Isi dihapus lagi jika metadata gagal disimpan."""
        artifact_id = str(uuid4())
        name = sanitize_filename(filename)
        size = await self._store.write(artifact_id, chunks, self._max_bytes)
        artifact = NewArtifact(
            artifact_id=artifact_id,
            owner_id=owner_id,
            name=name,
            mime_type=resolve_mime_type(content_type, name),
            size_bytes=size,
            storage_key=artifact_id,
            thread_id=thread_id,
        )
        try:
            record = await self._repository.add(artifact)
        except BaseException:
            await self._store.delete(artifact_id)
            raise
        logger.info("Stored artifact %s (%d bytes) for user %s", artifact_id, size, owner_id)
        return record

    async def get(self, artifact_id: str, owner_id: str) -> ArtifactRecord:
        """Metadata satu artifact milik `owner_id`.

        Raises:
            ArtifactNotFoundError: Jika artifact tidak ada atau milik user lain (404).
        """
        records = await self._repository.get_owned([artifact_id], owner_id)
        if not records:
            raise ArtifactNotFoundError(artifact_id)
        return records[0]

    async def open(self, record: ArtifactRecord) -> AsyncIterator[bytes]:
        """Buka isi artifact untuk diunduh.

        Raises:
            ArtifactContentMissingError: Jika isi file hilang dari store.
        """
        return await self._store.open(record.storage_key)

    async def delete(self, artifact_id: str, owner_id: str) -> None:
        """Hapus artifact milik `owner_id`, metadata lalu isinya.

        Raises:
            ArtifactNotFoundError: Jika artifact tidak ada atau milik user lain (404).
        """
        record = await self.get(artifact_id, owner_id)
        await self._repository.delete(record.artifact_id)
        await self._store.delete(record.storage_key)
        logger.info("Deleted artifact %s for user %s", artifact_id, owner_id)

    async def resolve_attachments(
        self, owner_id: str, artifact_ids: Sequence[str], thread_id: str | None
    ) -> list[ArtifactRecord]:
        """Periksa artifact yang akan dilampirkan ke pesan, urut sesuai request.

        Args:
            owner_id: Pengirim pesan.
            artifact_ids: ID dari request. Duplikat diabaikan.
            thread_id: Thread di request, atau `None` untuk thread baru.

        Returns:
            Artifact yang boleh dilampirkan, tanpa duplikat.

        Raises:
            ArtifactNotFoundError: Jika ada artifact yang tidak ada atau milik user lain (404).
            ArtifactThreadConflictError: Jika ada artifact yang tertaut ke thread lain (409).
        """
        unique_ids = list(dict.fromkeys(artifact_ids))
        records = await self._repository.get_owned(unique_ids, owner_id)
        by_id = {record.artifact_id: record for record in records}
        attachments: list[ArtifactRecord] = []
        for artifact_id in unique_ids:
            record = by_id.get(artifact_id)
            if record is None:
                raise ArtifactNotFoundError(artifact_id)
            if record.thread_id is not None and record.thread_id != thread_id:
                raise ArtifactThreadConflictError(artifact_id)
            attachments.append(record)
        return attachments

    async def link(self, attachments: Sequence[ArtifactRecord], thread_id: str) -> None:
        """Tautkan lampiran ke thread run, setelah kepemilikan thread diperiksa."""
        await self._repository.link_to_thread(
            [record.artifact_id for record in attachments], thread_id
        )

    async def workspace_paths(
        self, attachments: Sequence[ArtifactRecord], thread_id: str
    ) -> list[str]:
        """Path tujuan salinan lampiran di workspace thread, `uploads/<nama>` tanpa bentrok.

        Nama yang sudah dipakai file lain di `uploads/` diberi penanda dari ID artifact, jadi file
        lama tidak pernah tertimpa.
        """
        existing = [
            file.path for file in await self._workspace.list_files(thread_id, UPLOADS_FOLDER)
        ]
        paths: list[str] = []
        for record in attachments:
            path = str(PurePosixPath(UPLOADS_FOLDER, record.name))
            marker = record.artifact_id[:UPLOAD_MARKER_LENGTH]
            chosen = unique_path(path, [*existing, *paths], marker)
            paths.append(chosen)
        return paths

    async def copy_to_workspace(
        self, attachments: Sequence[ArtifactRecord], paths: Sequence[str], thread_id: str
    ) -> None:
        """Salin isi lampiran ke workspace thread, supaya agent bisa membacanya (F36).

        Raises:
            ArtifactContentMissingError: Jika isi lampiran hilang dari store.
        """
        for record, path in zip(attachments, paths, strict=True):
            chunks: list[bytes] = []
            async for chunk in await self._store.open(record.storage_key):
                chunks.append(chunk)
            await self._workspace.write(thread_id, path, b"".join(chunks))

    async def delete_thread_data(self, thread_id: str) -> None:
        """Hapus semua artifact satu thread. Dipanggil `ThreadRepository` saat thread dihapus."""
        records = await self._repository.delete_thread(thread_id)
        for record in records:
            await self._store.delete(record.storage_key)
        if records:
            logger.info("Deleted %d artifacts of thread %s", len(records), thread_id)


async def _single_chunk(content: bytes) -> AsyncIterator[bytes]:
    """Isi file yang sudah ada di memori, sebagai iterator potongan untuk `ArtifactStore`."""
    yield content


def artifact_ref(record: ArtifactRecord) -> ArtifactRef:
    """Referensi API untuk satu baris metadata artifact."""
    return ArtifactRef(
        id=record.artifact_id, name=record.name, mime_type=record.mime_type, size=record.size_bytes
    )


if __name__ == "__main__":
    print(sanitize_filename("../rahasia/laporan.pdf"), resolve_mime_type(None, "laporan.pdf"))
