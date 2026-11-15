import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from agent_service import export_contracts
from agent_service.service.contracts import OPENAPI_FILENAME, STREAM_EVENT_FILENAME


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    root_logger = logging.getLogger()
    handlers, level = root_logger.handlers[:], root_logger.level
    yield
    root_logger.handlers[:] = handlers
    root_logger.setLevel(level)


def test_export_writes_both_files(tmp_path: Path) -> None:
    exit_code = export_contracts.main(["--output-dir", str(tmp_path)])

    assert exit_code == export_contracts.EXIT_OK
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        OPENAPI_FILENAME,
        STREAM_EVENT_FILENAME,
    ]


def test_check_passes_after_export(tmp_path: Path) -> None:
    export_contracts.main(["--output-dir", str(tmp_path)])

    assert export_contracts.main(["--check", "--output-dir", str(tmp_path)]) == 0


def test_check_fails_on_stale_contract_without_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export_contracts.main(["--output-dir", str(tmp_path)])
    stale_file = tmp_path / OPENAPI_FILENAME
    stale_file.write_text("{}\n", encoding="utf-8")

    exit_code = export_contracts.main(["--check", "--output-dir", str(tmp_path)])

    assert exit_code == export_contracts.EXIT_STALE
    assert stale_file.read_text(encoding="utf-8") == "{}\n"
    assert "Run `uv run python -m agent_service.export_contracts`" in capsys.readouterr().err


def test_check_fails_when_contracts_are_missing(tmp_path: Path) -> None:
    exit_code = export_contracts.main(["--check", "--output-dir", str(tmp_path / "missing")])

    assert exit_code == export_contracts.EXIT_STALE
