"""Aturan artifact (FR-46, keputusan user F35): kepemilikan, lampiran pesan, dan penghapusan.

Artifact milik user lain diperlakukan sama dengan artifact yang tidak ada (404, NFR-9). Artifact
yang dilampirkan ke pesan tertaut ke thread itu, dan ikut terhapus saat thread dihapus.
"""

import logging
import mimetypes
import re
import unicodedata
from collections.abc import AsyncIterable, AsyncIterator, Sequence
from pathlib import PurePosixPath
from typing import Final
from uuid import uuid4

from agent_service.files.artifacts import ArtifactStore
from agent_service.memory.artifacts import ArtifactRecord, ArtifactRepository, NewArtifact
from agent_service.schema.artifacts import ArtifactRef

logger = logging.getLogger(__name__)

DEFAULT_FILENAME: Final = "file"
FILENAME_MAX_LENGTH: Final = 255
DEFAULT_MIME_TYPE: Final = "application/octet-stream"
# `type/subtype` tanpa parameter (RFC 6838, karakter yang diizinkan untuk nama tipe).
MIME_TYPE_PATTERN: Final = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")
# Kategori Unicode "Other" (kontrol, format, dan seterusnya) dibuang dari nama file.
UNICODE_OTHER_CATEGORY_PREFIX: Final = "C"


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
    ukuran). Dibuat sekali di lifespan, dan juga dipakai `ThreadRepository` untuk membersihkan
    artifact thread yang dihapus.
    """

    def __init__(
        self, repository: ArtifactRepository, store: ArtifactStore, max_bytes: int
    ) -> None:
        """Inisialisasi service.

        Args:
            repository: Metadata artifact di Postgres.
            store: Tempat isi file disimpan.
            max_bytes: Batas ukuran satu artifact (`ARTIFACT_MAX_BYTES`).
        """
        self._repository = repository
        self._store = store
        self._max_bytes = max_bytes

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

    async def delete_thread_data(self, thread_id: str) -> None:
        """Hapus semua artifact satu thread. Dipanggil `ThreadRepository` saat thread dihapus."""
        records = await self._repository.delete_thread(thread_id)
        for record in records:
            await self._store.delete(record.storage_key)
        if records:
            logger.info("Deleted %d artifacts of thread %s", len(records), thread_id)


def artifact_ref(record: ArtifactRecord) -> ArtifactRef:
    """Referensi API untuk satu baris metadata artifact."""
    return ArtifactRef(
        id=record.artifact_id, name=record.name, mime_type=record.mime_type, size=record.size_bytes
    )


def sanitize_filename(filename: str | None) -> str:
    """Nama file yang aman disimpan dan dikirim di header `Content-Disposition`.

    Path direktori dan karakter kontrol dibuang, dan nama dipotong ke `FILENAME_MAX_LENGTH` dengan
    ekstensi tetap dipertahankan.

    >>> sanitize_filename("../../etc/pass\\nwd.txt")
    'passwd.txt'
    >>> sanitize_filename("C:\\\\Users\\\\demo\\\\laporan Q3.pdf")
    'laporan Q3.pdf'
    >>> sanitize_filename("  ..  "), sanitize_filename(None)
    ('file', 'file')
    """
    if filename is None:
        return DEFAULT_FILENAME
    base = PurePosixPath(filename.replace("\\", "/")).name
    printable = "".join(
        char
        for char in unicodedata.normalize("NFC", base)
        if not unicodedata.category(char).startswith(UNICODE_OTHER_CATEGORY_PREFIX)
    )
    name = printable.strip().strip(".").strip()
    if not name:
        return DEFAULT_FILENAME
    return _truncate_keeping_suffix(name)


def resolve_mime_type(content_type: str | None, filename: str) -> str:
    """Tipe konten artifact: dari client jika valid, selain itu dari ekstensi nama file.

    >>> resolve_mime_type("Text/CSV; charset=utf-8", "a.csv")
    'text/csv'
    >>> resolve_mime_type(None, "chart.png")
    'image/png'
    >>> resolve_mime_type("application/octet-stream", "data.json")
    'application/json'
    >>> resolve_mime_type("bukan tipe", "tanpa-ekstensi")
    'application/octet-stream'
    """
    declared = "" if content_type is None else content_type.split(";")[0].strip().lower()
    if MIME_TYPE_PATTERN.fullmatch(declared) and declared != DEFAULT_MIME_TYPE:
        return declared
    guessed, _ = mimetypes.guess_type(filename, strict=False)
    return guessed or DEFAULT_MIME_TYPE


def _truncate_keeping_suffix(name: str) -> str:
    """Potong nama yang terlalu panjang, dengan ekstensi tetap di akhir."""
    if len(name) <= FILENAME_MAX_LENGTH:
        return name
    suffix = PurePosixPath(name).suffix
    if len(suffix) >= FILENAME_MAX_LENGTH:
        return name[:FILENAME_MAX_LENGTH]
    return name[: FILENAME_MAX_LENGTH - len(suffix)] + suffix


if __name__ == "__main__":
    print(sanitize_filename("../rahasia/laporan.pdf"), resolve_mime_type(None, "laporan.pdf"))
