"""`DockerSandbox`: satu container Docker per eksekusi, lewat Docker Engine API (F37).

Hanya dipakai `sandbox-runner`, satu-satunya service yang me-mount `docker.sock`. Setiap eksekusi:

1. create container dari image sandbox: tanpa jaringan, rootfs read-only, user non-root, tanpa
   capability, batas memori/CPU/proses, `/workspace` berupa volume anonim, `/tmp` berupa tmpfs;
2. salin file workspace + skrip ke `/workspace` (arsip tar) sebelum container dijalankan;
3. start, tunggu sampai selesai atau timeout (lalu kill);
4. baca log stdout/stderr dan salin `/workspace` keluar, ambil file yang baru atau berubah;
5. hapus container beserta volumenya, apa pun hasilnya.
"""

import asyncio
import io
import logging
import struct
import tarfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Final

import httpx

from agent_service.sandbox.model import (
    TRANSFER_MAX_BYTES,
    ExecutionRequest,
    ExecutionResult,
    Language,
    SandboxError,
)

logger = logging.getLogger(__name__)

DOCKER_BASE_URL: Final = "http://docker"
WORKSPACE_DIR: Final = "/workspace"
SCRIPT_FOLDER: Final = ".sandbox"
SCRIPT_NAMES: Final[Mapping[Language, str]] = {"python": "main.py", "shell": "main.sh"}
INTERPRETERS: Final[Mapping[Language, str]] = {"python": "python", "shell": "sh"}
# Sama dengan user di docker/sandbox.Dockerfile, pemilik `/workspace`.
SANDBOX_UID: Final = 10001
SANDBOX_USER: Final = f"{SANDBOX_UID}:{SANDBOX_UID}"
FILE_MODE: Final = 0o644
DIRECTORY_MODE: Final = 0o755
BYTES_PER_MEGABYTE: Final = 1024 * 1024
NANO_CPUS_PER_CPU: Final = 1_000_000_000
# Header frame log Docker: 1 byte stream, 3 byte kosong, 4 byte panjang (big-endian).
LOG_HEADER: Final = struct.Struct(">BxxxI")
STDOUT_STREAM: Final = 1
STDERR_STREAM: Final = 2
OUTPUT_MAX_BYTES: Final = 64 * 1024
HTTP_NOT_FOUND: Final = 404
REQUEST_TIMEOUT_SECONDS: Final = 30.0


@dataclass(frozen=True)
class ContainerLimits:
    """Batas sumber daya setiap container eksekusi (keputusan user F37)."""

    memory_megabytes: int = 512
    cpus: float = 1.0
    max_processes: int = 128
    tmp_megabytes: int = 64


class DockerSandbox:
    """`Sandbox` yang menjalankan kode di container Docker sekali pakai.

    Class karena memegang client HTTP ke Docker (dibuat sekali, ditutup lewat `aclose`), image,
    dan batas sumber daya.
    """

    def __init__(
        self, client: httpx.AsyncClient, image: str, limits: ContainerLimits | None = None
    ) -> None:
        """Inisialisasi sandbox.

        Args:
            client: Client ke Docker Engine API, misalnya lewat `unix_socket_client`.
            image: Image sandbox (Python + pandas + numpy + matplotlib, user non-root).
            limits: Batas sumber daya. Default: `ContainerLimits()`.
        """
        self._client = client
        self._image = image
        self._limits = ContainerLimits() if limits is None else limits

    async def aclose(self) -> None:
        """Tutup client HTTP ke Docker."""
        await self._client.aclose()

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Jalankan kode di container baru. Lihat `Sandbox.execute`."""
        try:
            container_id = await self._create(request.language)
        except httpx.HTTPError as error:
            raise SandboxError(f"Cannot create the sandbox container: {error}") from error
        try:
            return await self._run(container_id, request)
        except httpx.HTTPError as error:
            raise SandboxError(f"The sandbox failed: {error}") from error
        finally:
            await self._remove(container_id)

    async def _create(self, language: Language) -> str:
        """Buat container dengan semua batas keamanan, belum dijalankan."""
        script = f"{WORKSPACE_DIR}/{SCRIPT_FOLDER}/{SCRIPT_NAMES[language]}"
        response = await self._client.post(
            "/containers/create", json=self._container_spec([INTERPRETERS[language], script])
        )
        if response.status_code == HTTP_NOT_FOUND:
            raise SandboxError(f"Sandbox image {self._image!r} is not available")
        response.raise_for_status()
        return str(response.json()["Id"])

    def _container_spec(self, command: list[str]) -> dict[str, Any]:  # Any: JSON Docker API
        """Spesifikasi container: tanpa jaringan, rootfs read-only, non-root, dengan batas."""
        limits = self._limits
        return {
            "Image": self._image,
            "Cmd": command,
            "User": SANDBOX_USER,
            "WorkingDir": WORKSPACE_DIR,
            "NetworkDisabled": True,
            "Volumes": {WORKSPACE_DIR: {}},
            "HostConfig": {
                "NetworkMode": "none",
                "ReadonlyRootfs": True,
                "Memory": limits.memory_megabytes * BYTES_PER_MEGABYTE,
                "MemorySwap": limits.memory_megabytes * BYTES_PER_MEGABYTE,
                "NanoCpus": int(limits.cpus * NANO_CPUS_PER_CPU),
                "PidsLimit": limits.max_processes,
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges"],
                "Tmpfs": {"/tmp": f"size={limits.tmp_megabytes}m"},
            },
        }

    async def _run(self, container_id: str, request: ExecutionRequest) -> ExecutionResult:
        """Salin file masuk, jalankan sampai selesai atau timeout, lalu kumpulkan hasilnya."""
        script = {f"{SCRIPT_FOLDER}/{SCRIPT_NAMES[request.language]}": request.code.encode()}
        archive = pack_files({**request.files, **script})
        put = await self._client.put(
            f"/containers/{container_id}/archive",
            params={"path": WORKSPACE_DIR},
            content=archive,
            headers={"Content-Type": "application/x-tar"},
        )
        put.raise_for_status()
        (await self._client.post(f"/containers/{container_id}/start")).raise_for_status()
        exit_code, timed_out = await self._wait(container_id, request.timeout_seconds)
        stdout, stderr, truncated = await self._logs(container_id)
        changed, files_truncated = changed_files(request.files, await self._workspace(container_id))
        return ExecutionResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            output_truncated=truncated or files_truncated,
            files=changed,
        )

    async def _wait(self, container_id: str, timeout_seconds: int) -> tuple[int | None, bool]:
        """Tunggu container selesai. Saat timeout, container di-kill dan kode keluar kosong."""
        try:
            async with asyncio.timeout(timeout_seconds):
                response = await self._client.post(
                    f"/containers/{container_id}/wait", timeout=httpx.Timeout(None)
                )
        except TimeoutError:
            logger.info("Sandbox %s timed out after %ds", container_id[:12], timeout_seconds)
            await self._client.post(f"/containers/{container_id}/kill")
            return None, True
        response.raise_for_status()
        return int(response.json()["StatusCode"]), False

    async def _logs(self, container_id: str) -> tuple[str, str, bool]:
        """Stdout dan stderr container, masing-masing dipotong ke `OUTPUT_MAX_BYTES`."""
        response = await self._client.get(
            f"/containers/{container_id}/logs", params={"stdout": "1", "stderr": "1"}
        )
        response.raise_for_status()
        stdout, stderr = demux_logs(response.content)
        truncated = len(stdout) > OUTPUT_MAX_BYTES or len(stderr) > OUTPUT_MAX_BYTES
        return _decode(stdout), _decode(stderr), truncated

    async def _workspace(self, container_id: str) -> dict[str, bytes]:
        """Isi `/workspace` setelah eksekusi (tanpa folder skrip)."""
        response = await self._client.get(
            f"/containers/{container_id}/archive", params={"path": WORKSPACE_DIR}
        )
        response.raise_for_status()
        return unpack_files(response.content)

    async def _remove(self, container_id: str) -> None:
        """Hapus container beserta volume `/workspace`. Kegagalan hanya dicatat di log."""
        try:
            response = await self._client.delete(
                f"/containers/{container_id}", params={"force": "1", "v": "1"}
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("Cannot remove sandbox container %s", container_id[:12])


def unix_socket_client(socket_path: str) -> httpx.AsyncClient:
    """Client Docker Engine API lewat Unix socket (`/var/run/docker.sock`)."""
    transport = httpx.AsyncHTTPTransport(uds=socket_path)
    return httpx.AsyncClient(
        transport=transport, base_url=DOCKER_BASE_URL, timeout=REQUEST_TIMEOUT_SECONDS
    )


def pack_files(files: Mapping[str, bytes]) -> bytes:
    """Arsip tar berisi `files` (path relatif), dimiliki user sandbox.

    >>> sorted(unpack_files(pack_files({"a.txt": b"1", "d/b.txt": b"2"}), root=""))
    ['a.txt', 'd/b.txt']
    """
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for directory in _parent_directories(files):
            archive.addfile(_tar_entry(directory, tarfile.DIRTYPE, DIRECTORY_MODE, 0))
        for path, content in files.items():
            entry = _tar_entry(path, tarfile.REGTYPE, FILE_MODE, len(content))
            archive.addfile(entry, io.BytesIO(content))
    return buffer.getvalue()


def unpack_files(archive: bytes, root: str = "workspace") -> dict[str, bytes]:
    """File biasa dari arsip tar `GET /archive`, dengan path relatif terhadap `root`.

    Entri selain file biasa (symlink, device), path yang keluar dari `root`, dan folder skrip
    dilewati, supaya isi container tidak bisa menulis di luar workspace.

    >>> archive = pack_files({"workspace/a.csv": b"x", "workspace/.sandbox/main.py": b"y"})
    >>> unpack_files(archive)
    {'a.csv': b'x'}
    """
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r") as tar:
        for member in tar.getmembers():
            path = _relative_path(member.name, root)
            if path is None or not member.isfile():
                continue
            extracted = tar.extractfile(member)
            if extracted is not None:
                files[path] = extracted.read()
    return files


def changed_files(
    before: Mapping[str, bytes], after: Mapping[str, bytes]
) -> tuple[dict[str, bytes], bool]:
    """File yang baru atau isinya berubah, dibatasi total `TRANSFER_MAX_BYTES`.

    >>> changed_files({"a": b"1", "b": b"2"}, {"a": b"1", "b": b"3", "c": b"4"})
    ({'b': b'3', 'c': b'4'}, False)
    """
    changed: dict[str, bytes] = {}
    total = 0
    for path, content in sorted(after.items()):
        if before.get(path) == content:
            continue
        total += len(content)
        if total > TRANSFER_MAX_BYTES:
            return changed, True
        changed[path] = content
    return changed, False


def demux_logs(raw: bytes) -> tuple[bytes, bytes]:
    """Pisahkan frame log Docker (tanpa TTY) menjadi stdout dan stderr.

    >>> out = LOG_HEADER.pack(STDOUT_STREAM, 2) + b"hi"
    >>> demux_logs(out + LOG_HEADER.pack(STDERR_STREAM, 1) + b"!")
    (b'hi', b'!')
    """
    stdout = bytearray()
    stderr = bytearray()
    offset = 0
    while offset + LOG_HEADER.size <= len(raw):
        stream, size = LOG_HEADER.unpack_from(raw, offset)
        offset += LOG_HEADER.size
        payload = raw[offset : offset + size]
        offset += size
        target = stderr if stream == STDERR_STREAM else stdout
        target.extend(payload)
    return bytes(stdout), bytes(stderr)


def _relative_path(name: str, root: str) -> str | None:
    """Path relatif terhadap `root`, atau `None` untuk path di luar workspace atau folder skrip."""
    parts = PurePosixPath(name).parts
    if root:
        if not parts or parts[0] != root:
            return None
        parts = parts[1:]
    if not parts or ".." in parts or parts[0] in ("/", SCRIPT_FOLDER):
        return None
    return "/".join(parts)


def _parent_directories(files: Mapping[str, bytes]) -> list[str]:
    """Semua folder induk dari path file, urut dari yang terdangkal."""
    directories: set[str] = set()
    for path in files:
        for parent in PurePosixPath(path).parents:
            if str(parent) != ".":
                directories.add(str(parent))
    return sorted(directories, key=lambda directory: (directory.count("/"), directory))


def _tar_entry(name: str, kind: bytes, mode: int, size: int) -> tarfile.TarInfo:
    """Entri tar milik user sandbox, supaya bisa ditulis ulang oleh kode di container."""
    entry = tarfile.TarInfo(name)
    entry.type = kind
    entry.mode = mode
    entry.size = size
    entry.uid = SANDBOX_UID
    entry.gid = SANDBOX_UID
    return entry


def _decode(output: bytes) -> str:
    """Output proses sebagai teks, dipotong ke `OUTPUT_MAX_BYTES`."""
    return output[:OUTPUT_MAX_BYTES].decode("utf-8", errors="replace")
