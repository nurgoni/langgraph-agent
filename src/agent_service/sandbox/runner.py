"""Service `sandbox-runner` (keputusan user F37): satu-satunya proses yang memegang akses Docker.

App FastAPI kecil dengan `POST /execute` yang hanya menerima token bersama (`SANDBOX_TOKEN`).
Service ini tidak di-expose ke host; agent-service memanggilnya lewat jaringan internal compose.
"""

import logging
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Final

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent_service.core.constants import (
    DEFAULT_HOST,
    DEFAULT_LOG_LEVEL,
    DEFAULT_PORT,
    ENV_FILE,
    ENV_FILE_ENCODING,
    MAX_SANDBOX_TIMEOUT_SECONDS,
    LogLevel,
)
from agent_service.sandbox.docker import DockerSandbox, unix_socket_client
from agent_service.sandbox.model import ExecutionRequest, ExecutionResult, Sandbox, SandboxError

logger = logging.getLogger(__name__)

APP_TITLE: Final = "Sandbox Runner"
DEFAULT_SANDBOX_IMAGE: Final = "agent-service-sandbox:local"
DEFAULT_DOCKER_SOCKET: Final = "/var/run/docker.sock"
MIN_TOKEN_LENGTH: Final = 32

bearer_scheme = HTTPBearer(auto_error=False)


class SandboxRunnerSettings(BaseSettings):
    """Konfigurasi runner. Satu field = satu env var (nama field dalam huruf besar).

    >>> settings = SandboxRunnerSettings(_env_file=None, sandbox_token="t" * 32)
    >>> settings.sandbox_image, settings.docker_socket
    ('agent-service-sandbox:local', '/var/run/docker.sock')
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding=ENV_FILE_ENCODING,
        env_ignore_empty=True,
        extra="ignore",
    )

    sandbox_token: SecretStr = Field(min_length=MIN_TOKEN_LENGTH)
    sandbox_image: str = DEFAULT_SANDBOX_IMAGE
    docker_socket: str = DEFAULT_DOCKER_SOCKET
    sandbox_max_timeout_seconds: int = Field(default=MAX_SANDBOX_TIMEOUT_SECONDS, ge=1)
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    log_level: LogLevel = DEFAULT_LOG_LEVEL


def create_runner_app(settings: SandboxRunnerSettings, sandbox: Sandbox | None = None) -> FastAPI:
    """Bangun app runner. Client Docker dibuat di lifespan, bukan saat import.

    Args:
        settings: Konfigurasi runner.
        sandbox: Sandbox untuk test. Default: `DockerSandbox` lewat `docker_socket`.

    >>> app = create_runner_app(SandboxRunnerSettings(_env_file=None, sandbox_token="t" * 32))
    >>> app.title
    'Sandbox Runner'
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        if sandbox is not None:
            app.state.sandbox = sandbox
            yield
            return
        docker = DockerSandbox(unix_socket_client(settings.docker_socket), settings.sandbox_image)
        app.state.sandbox = docker
        logger.info("Sandbox runner uses image %s", settings.sandbox_image)
        try:
            yield
        finally:
            await docker.aclose()

    app = FastAPI(title=APP_TITLE, lifespan=lifespan)
    app.state.settings = settings
    app.add_api_route("/health", health, methods=["GET"])
    app.add_api_route("/execute", execute, methods=["POST"], dependencies=[Depends(require_token)])
    return app


def require_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> None:
    """Tolak request tanpa token bersama yang benar (401).

    Raises:
        HTTPException: Jika header `Authorization` tidak ada atau token salah.
    """
    settings: SandboxRunnerSettings = request.app.state.settings
    expected = settings.sandbox_token.get_secret_value()
    if credentials is None or not secrets.compare_digest(credentials.credentials, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid sandbox token")


async def health() -> dict[str, str]:
    """Health check untuk compose."""
    return {"status": "ok"}


async def execute(request: Request, execution: ExecutionRequest) -> ExecutionResult:
    """Jalankan satu eksekusi. Timeout dibatasi `SANDBOX_MAX_TIMEOUT_SECONDS`.

    Raises:
        HTTPException: 503 jika Docker gagal menjalankan container.
    """
    settings: SandboxRunnerSettings = request.app.state.settings
    sandbox: Sandbox = request.app.state.sandbox
    limited = min(execution.timeout_seconds, settings.sandbox_max_timeout_seconds)
    try:
        return await sandbox.execute(execution.model_copy(update={"timeout_seconds": limited}))
    except SandboxError as error:
        logger.warning("Sandbox execution failed: %s", error)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
