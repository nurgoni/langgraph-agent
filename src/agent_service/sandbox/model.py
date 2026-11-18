"""Model satu eksekusi sandbox: permintaan dan hasilnya (FR-49).

Model yang sama menjadi body HTTP antara agent-service (`RemoteSandbox`) dan `sandbox-runner`,
jadi isi file dikirim sebagai base64.

>>> request = ExecutionRequest(language="python", code="print(1)", files={"a.txt": b"hi"})
>>> request.model_dump(mode="json")["files"]
{'a.txt': 'aGk='}
>>> ExecutionRequest.model_validate_json(request.model_dump_json()).files
{'a.txt': b'hi'}
"""

from typing import Final, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

type Language = Literal["python", "shell"]

MAX_CODE_CHARS: Final = 100_000
# Batas total isi file yang disalin masuk atau keluar dari satu eksekusi.
TRANSFER_MAX_BYTES: Final = 50 * 1024 * 1024
# Isi file tetap bytes di Python, dan menjadi base64 hanya saat dikirim sebagai JSON.
BASE64_JSON: Final = ConfigDict(ser_json_bytes="base64", val_json_bytes="base64")


class ExecutionRequest(BaseModel):
    """Kode yang dijalankan beserta file workspace yang disalin masuk ke `/workspace`."""

    model_config = BASE64_JSON

    language: Language
    code: str = Field(min_length=1, max_length=MAX_CODE_CHARS)
    files: dict[str, bytes] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=60, ge=1)


class ExecutionResult(BaseModel):
    """Hasil satu eksekusi. `files` hanya berisi file yang baru atau berubah."""

    model_config = BASE64_JSON

    exit_code: int | None = Field(description="Kode keluar proses, kosong jika dihentikan.")
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    output_truncated: bool = False
    files: dict[str, bytes] = Field(default_factory=dict)


class SandboxError(RuntimeError):
    """Sandbox tidak bisa menjalankan kode (runner tidak terjangkau, Docker gagal)."""


# runtime_checkable: Pydantic memvalidasi `HarnessContext` di `ToolRuntime` dengan isinstance.
@runtime_checkable
class Sandbox(Protocol):
    """Tempat kode model dijalankan, terisolasi dari proses service."""

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Jalankan kode dan kembalikan output serta file yang berubah.

        Raises:
            SandboxError: Jika eksekusi tidak bisa dimulai atau diselesaikan.
        """
        ...
