"""Workspace per thread (FR-47, F36): sistem file virtual tempat agent membaca dan menulis file.

Path selalu relatif dan dinormalisasi ke bentuk POSIX. Path absolut, `..`, dan karakter kontrol
ditolak, jadi agent tidak pernah bisa keluar dari workspace-nya. Setiap thread punya workspace
sendiri; pemanggil (tool harness) mengambil `thread_id` dari config run yang ditetapkan service,
bukan dari model.
"""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Final, Protocol, runtime_checkable

PATH_MAX_LENGTH: Final = 512
# Kategori Unicode "Other" (kontrol, format) tidak boleh ada di path.
UNICODE_OTHER_CATEGORY_PREFIX: Final = "C"


class WorkspacePathError(ValueError):
    """Path kosong, absolut, keluar dari workspace, atau berisi karakter kontrol."""


class WorkspaceFileNotFoundError(LookupError):
    """File tidak ada di workspace thread."""

    def __init__(self, path: str) -> None:
        """Inisialisasi error dengan path yang dicari."""
        super().__init__(f"File {path!r} does not exist in the workspace")
        self.path = path


class WorkspaceFileTooLargeError(ValueError):
    """Isi file melebihi batas ukuran satu file workspace."""

    def __init__(self, path: str, max_bytes: int) -> None:
        """Inisialisasi error dengan path dan batas yang dilanggar."""
        super().__init__(f"File {path!r} is larger than the limit of {max_bytes} bytes")


@dataclass(frozen=True)
class WorkspaceFile:
    """Ringkasan satu file workspace (tanpa isi)."""

    path: str
    size_bytes: int
    updated_at: datetime


# runtime_checkable: Pydantic memvalidasi `HarnessContext` di `ToolRuntime` dengan isinstance.
@runtime_checkable
class Workspace(Protocol):
    """Penyimpanan file workspace per thread. Semua path sudah dinormalisasi pemanggil."""

    async def read(self, thread_id: str, path: str) -> bytes:
        """Isi satu file.

        Raises:
            WorkspaceFileNotFoundError: Jika file tidak ada.
        """
        ...

    async def write(self, thread_id: str, path: str, content: bytes) -> None:
        """Buat atau timpa satu file.

        Raises:
            WorkspaceFileTooLargeError: Jika isi melebihi batas ukuran file.
        """
        ...

    async def list_files(self, thread_id: str, prefix: str = "") -> list[WorkspaceFile]:
        """File di bawah `prefix` (folder), urut path. `prefix` kosong berarti semua file."""
        ...

    async def delete_thread_data(self, thread_id: str) -> None:
        """Hapus seluruh workspace thread. Dipakai saat thread dihapus."""
        ...


def normalize_workspace_path(path: str) -> str:
    """Path relatif POSIX di dalam workspace, tanpa `.` dan garis miring berlebih.

    >>> normalize_workspace_path("./data\\\\sales.csv")
    'data/sales.csv'
    >>> normalize_workspace_path("reports//q3/./summary.md")
    'reports/q3/summary.md'

    Raises:
        WorkspacePathError: Jika path kosong, absolut, berisi `..` atau karakter kontrol, atau
            terlalu panjang.
    """
    text = path.strip().replace("\\", "/")
    _reject_control_characters(path, text)
    candidate = PurePosixPath(text)
    if text.startswith("/") or _has_drive(text):
        raise WorkspacePathError(f"Path {path!r} must be relative to the workspace")
    if ".." in candidate.parts:
        raise WorkspacePathError(f"Path {path!r} must stay inside the workspace")
    parts = [part for part in candidate.parts if part != "."]
    if not parts:
        raise WorkspacePathError("Path must name a file inside the workspace")
    normalized = "/".join(parts)
    if len(normalized) > PATH_MAX_LENGTH:
        raise WorkspacePathError(f"Path is longer than {PATH_MAX_LENGTH} characters")
    return normalized


def normalize_workspace_folder(folder: str) -> str:
    """Prefix folder untuk listing: kosong untuk akar workspace, selain itu diakhiri `/`.

    >>> normalize_workspace_folder(""), normalize_workspace_folder("./reports/")
    ('', 'reports/')
    """
    if folder.strip() in ("", ".", "./", "/"):
        return ""
    return normalize_workspace_path(folder) + "/"


class InMemoryWorkspace:
    """`Workspace` di memori proses, untuk test dan contoh. Isinya hilang saat proses berhenti."""

    def __init__(self, max_file_bytes: int) -> None:
        """Inisialisasi workspace kosong.

        Args:
            max_file_bytes: Batas ukuran satu file.
        """
        self._max_file_bytes = max_file_bytes
        self._files: dict[tuple[str, str], tuple[bytes, datetime]] = {}

    async def read(self, thread_id: str, path: str) -> bytes:
        """Isi satu file. Lihat `Workspace.read`."""
        stored = self._files.get((thread_id, path))
        if stored is None:
            raise WorkspaceFileNotFoundError(path)
        return stored[0]

    async def write(self, thread_id: str, path: str, content: bytes) -> None:
        """Buat atau timpa satu file. Lihat `Workspace.write`."""
        if len(content) > self._max_file_bytes:
            raise WorkspaceFileTooLargeError(path, self._max_file_bytes)
        self._files[(thread_id, path)] = (content, datetime.now(UTC))

    async def list_files(self, thread_id: str, prefix: str = "") -> list[WorkspaceFile]:
        """File di bawah `prefix`. Lihat `Workspace.list_files`."""
        files: list[WorkspaceFile] = []
        for (owner_thread, path), (content, updated_at) in self._files.items():
            if owner_thread == thread_id and path.startswith(prefix):
                files.append(WorkspaceFile(path, len(content), updated_at))
        return sorted(files, key=lambda file: file.path)

    async def delete_thread_data(self, thread_id: str) -> None:
        """Hapus seluruh workspace thread. Lihat `Workspace.delete_thread_data`."""
        for key in [key for key in self._files if key[0] == thread_id]:
            del self._files[key]


def unique_path(path: str, existing: Sequence[str], marker: str) -> str:
    """`path`, atau `stem-marker.suffix` jika path itu sudah dipakai.

    >>> unique_path("uploads/a.csv", ["uploads/a.csv"], "1a2b")
    'uploads/a-1a2b.csv'
    >>> unique_path("uploads/a.csv", [], "1a2b")
    'uploads/a.csv'
    """
    if path not in existing:
        return path
    candidate = PurePosixPath(path)
    return str(candidate.with_name(f"{candidate.stem}-{marker}{candidate.suffix}"))


def _reject_control_characters(original: str, text: str) -> None:
    """Tolak path berisi karakter kontrol atau format Unicode."""
    for char in text:
        if unicodedata.category(char).startswith(UNICODE_OTHER_CATEGORY_PREFIX):
            raise WorkspacePathError(f"Path {original!r} contains control characters")


def _has_drive(text: str) -> bool:
    """Path bergaya Windows dengan huruf drive, misalnya `C:/data`."""
    return len(text) >= 2 and text[1] == ":" and text[0].isalpha()


if __name__ == "__main__":
    import asyncio

    async def _demo() -> None:
        workspace = InMemoryWorkspace(max_file_bytes=1024)
        path = normalize_workspace_path("notes/todo.md")
        await workspace.write("thread-1", path, b"- buy milk")
        print(await workspace.list_files("thread-1"))

    asyncio.run(_demo())
