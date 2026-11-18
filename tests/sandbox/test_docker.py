"""`DockerSandbox` terhadap Docker Engine API tiruan (tanpa Docker). Perilaku Docker asli dites di
e2e Compose."""

import asyncio
import io
import json
import tarfile
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from agent_service.sandbox.docker import (
    LOG_HEADER,
    STDERR_STREAM,
    STDOUT_STREAM,
    DockerSandbox,
    pack_files,
    unpack_files,
)
from agent_service.sandbox.model import ExecutionRequest, SandboxError

CONTAINER_ID = "c0ffee" * 10


@dataclass
class FakeDocker:
    """Docker Engine API tiruan yang mencatat setiap request."""

    workspace_after: dict[str, bytes] = field(default_factory=dict)
    exit_code: int = 0
    hang: bool = False
    image_missing: bool = False
    calls: list[tuple[str, str]] = field(default_factory=list)
    created: dict[str, Any] = field(default_factory=dict)  # Any: JSON spesifikasi container
    uploaded: dict[str, bytes] = field(default_factory=dict)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(
            (request.method, request.url.path.removeprefix(f"/containers/{CONTAINER_ID}"))
        )
        path = request.url.path
        if path == "/containers/create":
            return self._create(request)
        if path.endswith("/archive") and request.method == "PUT":
            self.uploaded = regular_files(request.content)
            return httpx.Response(200)
        if path.endswith("/wait"):
            if self.hang:
                await asyncio.sleep(3600)
            return httpx.Response(200, json={"StatusCode": self.exit_code})
        if path.endswith("/logs"):
            body = LOG_HEADER.pack(STDOUT_STREAM, 3) + b"4\n!" + LOG_HEADER.pack(STDERR_STREAM, 4)
            return httpx.Response(200, content=body + b"warn")
        if path.endswith("/archive"):
            files = {f"workspace/{name}": content for name, content in self.workspace_after.items()}
            return httpx.Response(200, content=pack_files(files))
        return httpx.Response(204)

    def _create(self, request: httpx.Request) -> httpx.Response:
        if self.image_missing:
            return httpx.Response(404, json={"message": "No such image"})
        self.created = json.loads(request.content)
        return httpx.Response(201, json={"Id": CONTAINER_ID})


def regular_files(archive: bytes) -> dict[str, bytes]:
    """Semua file biasa di arsip, tanpa penyaringan `unpack_files`."""
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r") as tar:
        for member in tar.getmembers():
            extracted = tar.extractfile(member) if member.isfile() else None
            if extracted is not None:
                files[member.name] = extracted.read()
    return files


def sandbox_for(docker: FakeDocker) -> DockerSandbox:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(docker.handle), base_url="http://docker"
    )
    return DockerSandbox(client, "sandbox:test")


async def test_container_is_locked_down() -> None:
    docker = FakeDocker()

    await sandbox_for(docker).execute(ExecutionRequest(language="python", code="print(4)"))

    host = docker.created["HostConfig"]
    assert docker.created["Cmd"] == ["python", "/workspace/.sandbox/main.py"]
    assert docker.created["NetworkDisabled"] is True
    assert docker.created["User"] == "10001:10001"
    assert host["NetworkMode"] == "none"
    assert host["ReadonlyRootfs"] is True
    assert host["CapDrop"] == ["ALL"]
    assert host["SecurityOpt"] == ["no-new-privileges"]
    assert (host["Memory"], host["NanoCpus"], host["PidsLimit"]) == (512 * 1024**2, 10**9, 128)


async def test_files_go_in_and_changed_files_come_out() -> None:
    docker = FakeDocker(
        workspace_after={"data.csv": b"a,b", "chart.png": b"\x89PNG", "new/x.txt": b"x"}
    )
    request = ExecutionRequest(language="shell", code="ls", files={"data.csv": b"a,b"})

    result = await sandbox_for(docker).execute(request)

    assert docker.uploaded == {"data.csv": b"a,b", ".sandbox/main.sh": b"ls"}
    assert docker.created["Cmd"] == ["sh", "/workspace/.sandbox/main.sh"]
    assert (result.exit_code, result.stdout, result.stderr) == (0, "4\n!", "warn")
    assert result.files == {"chart.png": b"\x89PNG", "new/x.txt": b"x"}


async def test_timeout_kills_the_container_and_still_removes_it() -> None:
    docker = FakeDocker(hang=True)

    result = await sandbox_for(docker).execute(
        ExecutionRequest(language="python", code="while True: pass", timeout_seconds=1)
    )

    assert (result.timed_out, result.exit_code) == (True, None)
    methods = [call for call in docker.calls if call[1] in ("/kill", "")]
    assert methods == [("POST", "/kill"), ("DELETE", "")]


async def test_missing_image_is_a_sandbox_error() -> None:
    with pytest.raises(SandboxError, match="not available"):
        await sandbox_for(FakeDocker(image_missing=True)).execute(
            ExecutionRequest(language="python", code="1")
        )


async def test_container_is_removed_when_docker_fails_midway() -> None:
    docker = FakeDocker()
    original = docker.handle

    async def failing_start(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/start"):
            docker.calls.append(("POST", "/start"))
            return httpx.Response(500, json={"message": "boom"})
        return await original(request)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(failing_start), base_url="http://docker"
    )
    with pytest.raises(SandboxError, match="The sandbox failed"):
        await DockerSandbox(client, "sandbox:test").execute(
            ExecutionRequest(language="python", code="1")
        )

    assert docker.calls[-1] == ("DELETE", "")


def test_unpack_skips_links_and_paths_outside_the_workspace() -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        link = tarfile.TarInfo("workspace/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        archive.addfile(link)
        for name in ("workspace/../escape.txt", "other/x.txt", "workspace/ok.txt"):
            entry = tarfile.TarInfo(name)
            entry.size = 2
            archive.addfile(entry, io.BytesIO(b"hi"))

    assert unpack_files(buffer.getvalue()) == {"ok.txt": b"hi"}
