"""Context runtime LangGraph untuk tool harness (F36): workspace dan penerbit artifact per run.

Service mengirim `HarnessContext` lewat `graph.ainvoke(..., context=...)` di setiap run, jadi
agent dibangun tanpa mengenal database. Tool membacanya dari `ToolRuntime.context`; run tanpa
context (test unit, sub-agent) membuat tool file menjawab "workspace not available".
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from agent_service.files.workspace import Workspace
from agent_service.memory.artifacts import ArtifactRecord
from agent_service.sandbox.model import Sandbox


# runtime_checkable: Pydantic memvalidasi `HarnessContext` di `ToolRuntime` dengan isinstance.
@runtime_checkable
class ArtifactPublisher(Protocol):
    """Membuat artifact baru dari isi file, misalnya file workspace yang dibagikan agent."""

    async def publish(
        self, owner_id: str, thread_id: str, filename: str, content: bytes
    ) -> ArtifactRecord:
        """Simpan `content` sebagai artifact milik `owner_id`, tertaut ke `thread_id`.

        Raises:
            ArtifactTooLargeError: Jika isi melebihi `ARTIFACT_MAX_BYTES`.
        """
        ...


@dataclass(frozen=True)
class HarnessContext:
    """Dependency tool harness untuk satu run. Dibuat sekali di lifespan dan dipakai semua run.

    `sandbox` kosong jika `SANDBOX_URL` tidak diisi; tool eksekusi kode lalu tidak tersedia.
    """

    workspace: Workspace
    artifacts: ArtifactPublisher
    sandbox: Sandbox | None = None
