import pytest
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from agent_service.core.settings import Settings
from agent_service.llm.factory import (
    DEFAULT_TEMPERATURE,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT_SECONDS,
    ModelFactory,
    ModelNotConfiguredError,
    UnknownModelError,
)
from agent_service.llm.fake import FakeModel

BASE_URL = "http://llm.test/v1"
API_KEY = "sk-test"
DEFAULT_MODEL = "gpt-test"
OTHER_MODEL = "gpt-other"


@pytest.fixture
def llm_settings() -> Settings:
    return Settings(
        _env_file=None,
        llm_base_url=BASE_URL,
        llm_api_key=API_KEY,
        default_model=DEFAULT_MODEL,
        available_models=[DEFAULT_MODEL, OTHER_MODEL],
    )


@pytest.fixture
def fake_settings() -> Settings:
    return Settings(_env_file=None, use_fake_model=True)


def test_none_resolves_to_default_model(llm_settings: Settings) -> None:
    model = ModelFactory(llm_settings).create()

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == DEFAULT_MODEL


def test_requested_model_is_used(llm_settings: Settings) -> None:
    model = ModelFactory(llm_settings).create(OTHER_MODEL)

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == OTHER_MODEL


def test_openai_compatible_model_uses_settings_and_constants(llm_settings: Settings) -> None:
    model = ModelFactory(llm_settings).create()

    assert isinstance(model, ChatOpenAI)
    assert model.openai_api_base == BASE_URL
    assert isinstance(model.openai_api_key, SecretStr)
    assert model.openai_api_key.get_secret_value() == API_KEY
    assert model.temperature == DEFAULT_TEMPERATURE
    assert model.request_timeout == LLM_TIMEOUT_SECONDS
    assert model.max_retries == LLM_MAX_RETRIES


def test_model_outside_allowlist_is_rejected(llm_settings: Settings) -> None:
    with pytest.raises(UnknownModelError) as error_info:
        ModelFactory(llm_settings).create("gpt-unknown")

    assert error_info.value.model_name == "gpt-unknown"
    assert error_info.value.available_models == [DEFAULT_MODEL, OTHER_MODEL]


def test_fake_is_rejected_when_not_in_allowlist(llm_settings: Settings) -> None:
    with pytest.raises(UnknownModelError):
        ModelFactory(llm_settings).create("fake")


def test_same_name_returns_cached_instance(llm_settings: Settings) -> None:
    factory = ModelFactory(llm_settings)

    assert factory.create(DEFAULT_MODEL) is factory.create()
    assert factory.create(OTHER_MODEL) is not factory.create(DEFAULT_MODEL)


def test_cache_is_per_factory_instance(llm_settings: Settings) -> None:
    assert ModelFactory(llm_settings).create() is not ModelFactory(llm_settings).create()


def test_fake_mode_returns_fake_model(fake_settings: Settings) -> None:
    assert isinstance(ModelFactory(fake_settings).create(), FakeModel)


def test_real_model_without_llm_config_is_not_configured() -> None:
    settings = Settings(
        _env_file=None, use_fake_model=True, available_models=["fake", DEFAULT_MODEL]
    )

    with pytest.raises(ModelNotConfiguredError, match="LLM_BASE_URL"):
        ModelFactory(settings).create(DEFAULT_MODEL)


def test_unvalidated_settings_without_default_model_are_rejected() -> None:
    settings = Settings.model_construct(default_model=None, available_models=[])

    with pytest.raises(ModelNotConfiguredError):
        ModelFactory(settings)


async def test_fake_model_answers_without_network(fake_settings: Settings) -> None:
    message = await ModelFactory(fake_settings).create().ainvoke("Halo")

    assert message.content
