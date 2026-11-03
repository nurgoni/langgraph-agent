import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI

from agent_service import run_service

TEST_PORT = 9123


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    root_logger = logging.getLogger()
    handlers, level = root_logger.handlers[:], root_logger.level
    yield
    root_logger.handlers[:] = handlers
    root_logger.setLevel(level)


def test_main_runs_uvicorn_with_settings_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("USE_FAKE_MODEL", "true")
    monkeypatch.setenv("PORT", str(TEST_PORT))
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    calls: list[tuple[object, dict[str, object]]] = []
    monkeypatch.setattr(
        run_service.uvicorn, "run", lambda app, **kwargs: calls.append((app, kwargs))
    )

    run_service.main()

    [(app, kwargs)] = calls
    assert isinstance(app, FastAPI)
    assert kwargs["port"] == TEST_PORT
    assert kwargs["log_config"] is None
    assert logging.getLogger().level == logging.DEBUG
