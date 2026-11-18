"""Penyimpanan isi file artifact (FR-46, F35).

`ArtifactStore` berupa protocol supaya penyimpanan S3-compatible (backlog B7) bisa ditambah tanpa
mengubah pemanggil. `LocalArtifactStore` menyimpan setiap artifact sebagai satu file di direktori
lokal (volume di compose). Metadata (nama, tipe, pemilik) tidak disimpan di sini, tetapi di
Postgres (`memory/artifacts.py`).
"""

import logging
import re
from collections.abc import AsyncIterable, AsyncIterator
from pathlib import Path
from typing import Final, Protocol

import anyio

logger = logging.getLogger(__name__)

CHUNK_SIZE_BYTES: Final = 64 * 1024
PARTIAL_SUFFIX: Final = ".part"
# Kunci dibuat service (UUID), tetapi tetap divalidasi supaya tidak bisa keluar dari direktori.
STORAGE_KEY_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,127}$")


class ArtifactTooLargeError(ValueError):
    """Isi artifact melebihi batas ukuran (`ARTIFACT_MAX_BYTES`)."""

    def __init__(self, max_bytes: int) -> None:
        """Inisialisasi error dengan batas yang dilanggar."""
        super().__init__(f"File is larger than the limit of {max_bytes} bytes")
        self.max_bytes = max_bytes


class ArtifactContentMissingError(LookupError):
    """Isi file artifact tidak ada di store, padahal metadatanya ada."""

    def __init__(self, key: str) -> None:
        """Inisialisasi error dengan kunci yang hilang."""
        super().__init__(f"Artifact content {key!r} is missing")


class InvalidStorageKeyError(ValueError):
    """Kunci penyimpanan tidak cocok `STORAGE_KEY_PATTERN`."""


class ArtifactStore(Protocol):
    """Tempat isi file artifact disimpan, dibaca, dan dihapus."""

    async def write(self, key: str, chunks: AsyncIterable[bytes], max_bytes: int) -> int:
        """Tulis isi artifact dari potongan byte.

        Returns:
            Ukuran isi yang tersimpan, dalam byte.

        Raises:
            ArtifactTooLargeError: Jika isi melebihi `max_bytes`; tidak ada yang tersimpan.
        """
        ...

    async def open(self, key: str) -> AsyncIterator[bytes]:
        """Buka isi artifact untuk dibaca per potongan.

        Raises:
            ArtifactContentMissingError: Jika isi tidak ada.
        """
        ...

    async def delete(self, key: str) -> None:
        """Hapus isi artifact. Kunci yang tidak ada diabaikan."""
        ...


class LocalArtifactStore:
    """`ArtifactStore` di direktori lokal: satu file per artifact, bernama kunci penyimpanannya.

    Isi ditulis ke file `.part` lalu di-rename, jadi pembaca tidak pernah melihat file setengah
    jadi, dan upload yang gagal tidak meninggalkan file.
    """

    def __init__(self, root: Path) -> None:
        """Inisialisasi store.

        Args:
            root: Direktori penyimpanan. Dibuat oleh `prepare()`.
        """
        self._root = anyio.Path(root)

    async def prepare(self) -> None:
        """Buat direktori penyimpanan jika belum ada. Dipanggil sekali di lifespan."""
        await self._root.mkdir(parents=True, exist_ok=True)
        logger.info("Artifact store at %s", self._root)

    async def write(self, key: str, chunks: AsyncIterable[bytes], max_bytes: int) -> int:
        """Tulis isi artifact. Lihat `ArtifactStore.write`."""
        target = self._path(key)
        partial = target.with_name(target.name + PARTIAL_SUFFIX)
        try:
            size = await self._write_partial(partial, chunks, max_bytes)
        except BaseException:
            await partial.unlink(missing_ok=True)
            raise
        await partial.rename(target)
        return size

    async def open(self, key: str) -> AsyncIterator[bytes]:
        """Buka isi artifact. Lihat `ArtifactStore.open`."""
        path = self._path(key)
        try:
            file = await anyio.open_file(path, "rb")
        except FileNotFoundError as error:
            raise ArtifactContentMissingError(key) from error
        return _read_chunks(file)

    async def delete(self, key: str) -> None:
        """Hapus isi artifact. Lihat `ArtifactStore.delete`."""
        await self._path(key).unlink(missing_ok=True)

    async def _write_partial(
        self, partial: anyio.Path, chunks: AsyncIterable[bytes], max_bytes: int
    ) -> int:
        """Tulis semua potongan ke file sementara sambil menghitung ukurannya."""
        size = 0
        async with await anyio.open_file(partial, "wb") as file:
            async for chunk in chunks:
                size += len(chunk)
                if size > max_bytes:
                    raise ArtifactTooLargeError(max_bytes)
                await file.write(chunk)
        return size

    def _path(self, key: str) -> anyio.Path:
        """Path file untuk kunci yang sudah divalidasi.

        Raises:
            InvalidStorageKeyError: Jika kunci bisa keluar dari direktori penyimpanan.
        """
        if STORAGE_KEY_PATTERN.fullmatch(key) is None:
            raise InvalidStorageKeyError(f"Invalid artifact storage key: {key!r}")
        return self._root / key


async def _read_chunks(file: anyio.AsyncFile[bytes]) -> AsyncIterator[bytes]:
    """Baca file per `CHUNK_SIZE_BYTES`, lalu tutup file (juga saat pembaca berhenti di tengah)."""
    async with file:
        while chunk := await file.read(CHUNK_SIZE_BYTES):
            yield chunk


if __name__ == "__main__":
    import tempfile

    async def _demo() -> None:
        async def chunks() -> AsyncIterator[bytes]:
            yield b"hello "
            yield b"artifact"

        store = LocalArtifactStore(Path(tempfile.mkdtemp()))
        await store.prepare()
        print(await store.write("demo-key", chunks(), max_bytes=1024))
        async for chunk in await store.open("demo-key"):
            print(chunk)

    anyio.run(_demo)
