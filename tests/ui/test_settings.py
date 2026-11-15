from collections.abc import Iterator

import pytest

from agent_service.ui.settings import DEFAULT_AGENT_URL, UiSettings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in UiSettings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    yield


def test_defaults_point_to_local_service() -> None:
    assert UiSettings(_env_file=None).agent_url == DEFAULT_AGENT_URL


def test_values_come_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_URL", "http://agent:8080")

    assert UiSettings(_env_file=None).agent_url == "http://agent:8080"


def test_service_only_variables_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "not-for-ui")
    monkeypatch.setenv("JWT_SECRET", "not-for-ui-either-at-least-32-chars")

    dumped = UiSettings(_env_file=None).model_dump()

    assert "llm_api_key" not in dumped
    assert "jwt_secret" not in dumped
