"""Kontrak API yang dipublikasikan di `contracts/` (FR-35), untuk generate tipe client (F32).

- `openapi.json`: OpenAPI dari app FastAPI, dibuat tanpa lifespan (tanpa database dan LLM).
- `stream-event.schema.json`: JSON Schema satu frame SSE `/stream` (`StreamEvent`).

Isi file deterministik (key terurut, indentasi tetap, LF, newline di akhir), jadi file hanya
berubah jika kontraknya berubah. CI menjalankan `export_contracts --check`.
"""

import json
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any, Final

from pydantic import SecretStr

from agent_service.agents.chatbot import ChatbotAgent
from agent_service.core.settings import Settings
from agent_service.schema.stream import STREAM_DONE_MARKER, STREAM_EVENT_ADAPTER
from agent_service.service.app import create_app

PACKAGE_NAME: Final = "agent-service"
OPENAPI_FILENAME: Final = "openapi.json"
STREAM_EVENT_FILENAME: Final = "stream-event.schema.json"
JSON_SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"
STREAM_EVENT_TITLE: Final = "StreamEvent"
STREAM_EVENT_DESCRIPTION: Final = (
    "One Server-Sent Event frame from POST /{agent_id}/stream. Each frame is sent as "
    f"`data: <json>`, and the stream always ends with the literal `data: {STREAM_DONE_MARKER}`, "
    "which is not JSON."
)
JSON_INDENT: Final = 2
# Settings tiruan: OpenAPI tidak bergantung pada konfigurasi, jadi `.env` developer tidak dibaca.
PLACEHOLDER_JWT_SECRET: Final = "contract-export-placeholder-secret"


@dataclass(frozen=True)
class ContractFile:
    """Satu file kontrak: nama file dan isinya yang sudah diserialisasi."""

    filename: str
    content: str


def openapi_document() -> dict[str, Any]:  # Any: dokumen OpenAPI berbentuk JSON bebas
    """OpenAPI service, dengan versi package sebagai `info.version`.

    >>> document = openapi_document()
    >>> document["info"]["title"], "/auth/login" in document["paths"]
    ('Agent Service', True)
    """
    settings = Settings(
        _env_file=None, use_fake_model=True, jwt_secret=SecretStr(PLACEHOLDER_JWT_SECRET)
    )
    app = create_app(settings, agents=[ChatbotAgent()])
    app.version = version(PACKAGE_NAME)
    return app.openapi()


def stream_event_schema() -> dict[str, Any]:  # Any: JSON Schema berbentuk JSON bebas
    """JSON Schema satu frame `StreamEvent`, termasuk penjelasan penanda akhir stream.

    >>> schema = stream_event_schema()
    >>> schema["title"], sorted(schema["discriminator"]["mapping"])
    ('StreamEvent', ['error', 'message', 'reasoning', 'token'])
    """
    schema = STREAM_EVENT_ADAPTER.json_schema()
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "title": STREAM_EVENT_TITLE,
        "description": STREAM_EVENT_DESCRIPTION,
        **schema,
    }


def to_json(document: dict[str, Any]) -> str:  # Any: dokumen JSON bebas
    """Serialisasi deterministik: key terurut, indentasi 2, UTF-8 apa adanya, newline di akhir.

    >>> to_json({"b": 1, "a": "é"})
    '{\\n  "a": "é",\\n  "b": 1\\n}\\n'
    """
    return json.dumps(document, indent=JSON_INDENT, sort_keys=True, ensure_ascii=False) + "\n"


def build_contracts() -> list[ContractFile]:
    """Semua file kontrak dengan isi terbaru dari kode."""
    return [
        ContractFile(OPENAPI_FILENAME, to_json(openapi_document())),
        ContractFile(STREAM_EVENT_FILENAME, to_json(stream_event_schema())),
    ]


def write_contracts(output_dir: Path, contracts: list[ContractFile]) -> None:
    """Tulis file kontrak dengan line ending LF, membuat folder jika belum ada."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for contract in contracts:
        (output_dir / contract.filename).write_text(
            contract.content, encoding="utf-8", newline="\n"
        )


def stale_contracts(output_dir: Path, contracts: list[ContractFile]) -> list[str]:
    """Nama file kontrak yang tidak ada atau isinya berbeda dari kode.

    Args:
        output_dir: Folder `contracts/`.
        contracts: Hasil `build_contracts()`.

    Returns:
        Nama file yang perlu di-export ulang. Kosong berarti kontrak sinkron.
    """
    stale: list[str] = []
    for contract in contracts:
        path = output_dir / contract.filename
        if not path.is_file() or path.read_text(encoding="utf-8") != contract.content:
            stale.append(contract.filename)
    return stale
