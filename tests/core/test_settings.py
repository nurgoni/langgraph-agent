import importlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_service.core.constants import DEFAULT_PORT, FAKE_MODEL_NAME
from agent_service.core.settings import Settings

REAL_LLM_ENV = {
    "LLM_BASE_URL": "https://llm.example/v1",
    "LLM_API_KEY": "sk-test",
    "DEFAULT_MODEL": "gpt-test",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hapus semua env var milik Settings agar test tidak dipengaruhi mesin developer."""
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)


def set_env(monkeypatch: pytest.MonkeyPatch, values: dict[str, str]) -> None:
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_module_import_creates_no_settings_instance() -> None:
    module = importlib.import_module("agent_service.core.settings")

    instances = [value for value in vars(module).values() if isinstance(value, Settings)]

    assert instances == []


def test_fake_mode_needs_no_llm_config() -> None:
    settings = Settings(_env_file=None, use_fake_model=True)

    assert settings.default_model == FAKE_MODEL_NAME
    assert settings.available_models == [FAKE_MODEL_NAME]


def test_missing_llm_config_lists_every_missing_env_var() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    message = str(error.value)
    for env_name in REAL_LLM_ENV:
        assert env_name in message


def test_reads_llm_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, REAL_LLM_ENV)

    settings = Settings(_env_file=None)

    assert settings.llm_base_url == "https://llm.example/v1"
    assert settings.default_model == "gpt-test"
    assert settings.available_models == ["gpt-test"]
    assert settings.port == DEFAULT_PORT


def test_api_key_is_hidden_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, REAL_LLM_ENV)

    settings = Settings(_env_file=None)

    assert "sk-test" not in repr(settings)
    assert settings.llm_api_key is not None
    assert settings.llm_api_key.get_secret_value() == "sk-test"


def test_available_models_is_split_on_commas(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, REAL_LLM_ENV | {"AVAILABLE_MODELS": " gpt-test, gpt-big ,,"})

    settings = Settings(_env_file=None)

    assert settings.available_models == ["gpt-test", "gpt-big"]


def test_default_model_outside_allowlist_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, REAL_LLM_ENV | {"AVAILABLE_MODELS": "gpt-big"})

    with pytest.raises(ValidationError, match="not in AVAILABLE_MODELS"):
        Settings(_env_file=None)


def test_fake_mode_keeps_real_default_and_adds_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, REAL_LLM_ENV | {"USE_FAKE_MODEL": "true"})

    settings = Settings(_env_file=None)

    assert settings.default_model == "gpt-test"
    assert settings.available_models == ["gpt-test", FAKE_MODEL_NAME]


def test_empty_env_value_counts_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, {"USE_FAKE_MODEL": "true", "DEFAULT_MODEL": ""})

    settings = Settings(_env_file=None)

    assert settings.default_model == FAKE_MODEL_NAME


@pytest.mark.parametrize("port", ["0", "65536"])
def test_port_outside_valid_range_is_rejected(monkeypatch: pytest.MonkeyPatch, port: str) -> None:
    set_env(monkeypatch, {"USE_FAKE_MODEL": "true", "PORT": port})

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_invalid_log_level_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, {"USE_FAKE_MODEL": "true", "LOG_LEVEL": "LOUD"})

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_reads_values_from_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("USE_FAKE_MODEL=true\nPORT=9000\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.use_fake_model is True
    assert settings.port == 9000
