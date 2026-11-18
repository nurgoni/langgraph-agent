"""Service `sandbox-runner` dan `RemoteSandbox` lewat HTTP in-process (F37)."""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from agent_service.sandbox.fake import FakeSandbox
from agent_service.sandbox.model import ExecutionRequest, ExecutionResult, SandboxError
from agent_service.sandbox.remote import RemoteSandbox
from agent_service.sandbox.runner import SandboxRunnerSettings, create_runner_app

TOKEN = "runner-token-with-at-least-32-characters"
MAX_TIMEOUT = 20
BINARY = bytes(range(256))


def echo_files(request: ExecutionRequest) -> ExecutionResult:
    """Kembalikan file masuk dengan nama baru, plus timeout yang diterima sandbox."""
    renamed = {f"out/{path}": content for path, content in request.files.items()}
    return ExecutionResult(exit_code=0, stdout=str(request.timeout_seconds), files=renamed)


@pytest.fixture
def fake_sandbox() -> FakeSandbox:
    return FakeSandbox(echo_files)


@pytest.fixture
async def runner(fake_sandbox: FakeSandbox) -> AsyncIterator[FastAPI]:
    settings = SandboxRunnerSettings(
        _env_file=None, sandbox_token=TOKEN, sandbox_max_timeout_seconds=MAX_TIMEOUT
    )
    app = create_runner_app(settings, sandbox=fake_sandbox)
    async with app.router.lifespan_context(app):
        yield app


def remote(app: FastAPI, token: str = TOKEN) -> RemoteSandbox:
    return RemoteSandbox("http://runner", token, transport=ASGITransport(app=app))


async def test_files_round_trip_as_bytes(runner: FastAPI, fake_sandbox: FakeSandbox) -> None:
    request = ExecutionRequest(language="python", code="print(1)", files={"data.bin": BINARY})

    async with remote(runner) as sandbox:
        result = await sandbox.execute(request)

    assert fake_sandbox.requests[0].files == {"data.bin": BINARY}
    assert result.files == {"out/data.bin": BINARY}


async def test_runner_caps_the_timeout(runner: FastAPI) -> None:
    async with remote(runner) as sandbox:
        result = await sandbox.execute(
            ExecutionRequest(language="shell", code="sleep 1", timeout_seconds=MAX_TIMEOUT * 10)
        )

    assert result.stdout == str(MAX_TIMEOUT)


async def test_wrong_token_is_rejected(runner: FastAPI, fake_sandbox: FakeSandbox) -> None:
    async with remote(runner, token="wrong") as sandbox:
        with pytest.raises(SandboxError, match="status 401"):
            await sandbox.execute(ExecutionRequest(language="python", code="1"))

    assert fake_sandbox.requests == []


async def test_docker_failures_become_sandbox_errors() -> None:
    def fail(request: ExecutionRequest) -> ExecutionResult:
        raise SandboxError("Sandbox image 'missing' is not available")

    app = create_runner_app(
        SandboxRunnerSettings(_env_file=None, sandbox_token=TOKEN), sandbox=FakeSandbox(fail)
    )
    async with app.router.lifespan_context(app), remote(app) as sandbox:
        with pytest.raises(SandboxError, match="status 503"):
            await sandbox.execute(ExecutionRequest(language="python", code="1"))


async def test_unreachable_runner_is_a_sandbox_error() -> None:
    async with RemoteSandbox("http://127.0.0.1:9", TOKEN) as sandbox:
        with pytest.raises(SandboxError, match="Cannot reach the sandbox runner"):
            await sandbox.execute(ExecutionRequest(language="python", code="1"))
