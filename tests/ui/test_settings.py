from collections.abc import Iterator

import pytest

from agent_service.ui.settings import DEFAULT_AGENT_URL, UiSettings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in UiSettings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    yield


def test_defaults_point_to_local_service() -> None:
    settings = UiSettings(_env_file=None)

    assert settings.agent_url == DEFAULT_AGENT_URL
    assert settings.auth_token() is None


def test_values_come_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_URL", "http://agent:8080")
    monkeypatch.setenv("AUTH_SECRET", "s3cret")

    settings = UiSettings(_env_file=None)

    assert settings.agent_url == "http://agent:8080"
    assert settings.auth_token() == "s3cret"


def test_service_only_variables_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "not-for-ui")

    assert "llm_api_key" not in UiSettings(_env_file=None).model_dump()
