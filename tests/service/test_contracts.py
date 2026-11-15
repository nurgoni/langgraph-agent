import json
import re
from pathlib import Path

import pytest

from agent_service.schema.headers import THREAD_ID_HEADER
from agent_service.service.contracts import (
    OPENAPI_FILENAME,
    STREAM_EVENT_FILENAME,
    build_contracts,
    openapi_document,
    stale_contracts,
    stream_event_schema,
    write_contracts,
)

PUBLISHED_DIR = Path(__file__).resolve().parents[2] / "contracts"
RUN_PATHS = ["/invoke", "/{agent_id}/invoke", "/stream", "/{agent_id}/stream"]
# Penanda docstring internal (doctest, bagian Google-style) yang tidak boleh ikut ke kontrak.
INTERNAL_DOC_MARKERS = re.compile(r">>>|\bArgs:|\bRaises:|\bReturns:")


def test_published_contracts_match_the_code() -> None:
    stale = stale_contracts(PUBLISHED_DIR, build_contracts())

    assert stale == [], (
        f"contracts/ is out of date ({stale}). "
        "Run `uv run python -m agent_service.export_contracts` and commit the result."
    )


def test_export_is_deterministic() -> None:
    assert build_contracts() == build_contracts()


def test_files_use_sorted_keys_and_trailing_newline() -> None:
    for contract in build_contracts():
        document = json.loads(contract.content)

        assert contract.content.endswith("}\n")
        assert "\r" not in contract.content
        assert list(document) == sorted(document)


def test_stale_and_missing_files_are_reported(tmp_path: Path) -> None:
    contracts = build_contracts()
    write_contracts(tmp_path, contracts)
    assert stale_contracts(tmp_path, contracts) == []

    (tmp_path / OPENAPI_FILENAME).write_text("{}\n", encoding="utf-8")
    (tmp_path / STREAM_EVENT_FILENAME).unlink()

    assert stale_contracts(tmp_path, contracts) == [OPENAPI_FILENAME, STREAM_EVENT_FILENAME]


def test_contracts_carry_no_internal_docstrings() -> None:
    for contract in build_contracts():
        assert INTERNAL_DOC_MARKERS.findall(contract.content) == [], contract.filename


def test_openapi_has_no_user_id_parameters_or_fields() -> None:
    document = openapi_document()

    request_schemas = ["UserInput", "StreamInput", "ChatHistoryInput", "ThreadRenameInput"]
    for name in request_schemas:
        assert "user_id" not in document["components"]["schemas"][name]["properties"]
    for operations in document["paths"].values():
        for operation in operations.values():
            names = [parameter["name"] for parameter in operation.get("parameters", [])]
            assert "user_id" not in names


@pytest.mark.parametrize("path", RUN_PATHS)
def test_run_endpoints_document_thread_id_header(path: str) -> None:
    response = openapi_document()["paths"][path]["post"]["responses"]["200"]

    assert THREAD_ID_HEADER in response["headers"]


def test_openapi_version_follows_package_version() -> None:
    from importlib.metadata import version

    assert openapi_document()["info"]["version"] == version("agent-service")


def test_protected_endpoints_declare_bearer_auth() -> None:
    document = openapi_document()

    assert document["paths"]["/info"]["get"]["security"] == [{"HTTPBearer": []}]
    assert "security" not in document["paths"]["/health"]["get"]
    assert "security" not in document["paths"]["/auth/login"]["post"]


def test_stream_event_schema_describes_every_frame_type() -> None:
    schema = stream_event_schema()

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert sorted(schema["discriminator"]["mapping"]) == ["error", "message", "reasoning", "token"]
    assert "[DONE]" in schema["description"]
