"""`RemoteSandbox`: client agent-service ke service `sandbox-runner` (keputusan user F37).

Agent-service tidak pernah memegang akses Docker. Setiap eksekusi dikirim ke runner lewat HTTP
internal compose dengan token bersama (`SANDBOX_TOKEN`).
"""

import logging
from typing import Final, Self

import httpx

from agent_service.sandbox.model import ExecutionRequest, ExecutionResult, SandboxError

logger = logging.getLogger(__name__)

EXECUTE_PATH: Final = "/execute"
# Waktu tambahan di luar timeout eksekusi: membuat container, menyalin file, dan menghapusnya.
OVERHEAD_SECONDS: Final = 30.0
CONNECT_TIMEOUT_SECONDS: Final = 5.0


class RemoteSandbox:
    """`Sandbox` yang meneruskan eksekusi ke `sandbox-runner`.

    Class karena memegang satu `httpx.AsyncClient` yang dipakai ulang dan ditutup di lifespan
    (`async with RemoteSandbox(...)`).
    """

    def __init__(
        self, base_url: str, token: str, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        """Inisialisasi client.

        Args:
            base_url: URL runner, misalnya `http://sandbox-runner:8080`.
            token: Token bersama yang diperiksa runner.
            transport: Transport httpx, bisa diganti di test.
        """
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            transport=transport,
        )

    async def __aenter__(self) -> Self:
        """Pakai client sampai blok `async with` selesai."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Tutup client HTTP."""
        await self._client.aclose()

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Jalankan kode lewat runner. Lihat `Sandbox.execute`."""
        timeout = httpx.Timeout(
            request.timeout_seconds + OVERHEAD_SECONDS, connect=CONNECT_TIMEOUT_SECONDS
        )
        try:
            response = await self._client.post(
                EXECUTE_PATH,
                content=request.model_dump_json(),
                timeout=timeout,
                headers={"Content-Type": "application/json"},
            )
        except httpx.HTTPError as error:
            raise SandboxError(f"Cannot reach the sandbox runner: {error}") from error
        if not response.is_success:
            logger.warning("Sandbox runner answered %d: %s", response.status_code, response.text)
            raise SandboxError(f"The sandbox runner failed with status {response.status_code}")
        return ExecutionResult.model_validate_json(response.content)
