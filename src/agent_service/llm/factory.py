"""Pembuatan chat model per nama, dibatasi oleh allowlist di `Settings`."""

from typing import Final

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from agent_service.core.constants import FAKE_MODEL_NAME
from agent_service.core.settings import Settings
from agent_service.llm.fake import FakeModel

LLM_TIMEOUT_SECONDS: Final = 60.0
LLM_MAX_RETRIES: Final = 3
DEFAULT_TEMPERATURE: Final = 0.5


class ModelError(Exception):
    """Error dasar untuk pembuatan model."""


class UnknownModelError(ModelError):
    """Nama model tidak ada di allowlist `AVAILABLE_MODELS`."""

    def __init__(self, model_name: str, available_models: list[str]) -> None:
        """Inisialisasi error.

        Args:
            model_name: Nama model yang diminta.
            available_models: Allowlist model yang berlaku.
        """
        super().__init__(f"Unknown model {model_name!r}. Available models: {available_models}")
        self.model_name = model_name
        self.available_models = available_models


class ModelNotConfiguredError(ModelError):
    """Model ada di allowlist, tapi konfigurasi yang dibutuhkan untuk membuatnya belum ada."""


class ModelFactory:
    """Membuat chat model berdasarkan nama, dan menyimpan instance per nama untuk di-reuse.

    Nama `fake` menghasilkan `FakeModel`. Nama lain menghasilkan `ChatOpenAI` yang diarahkan
    ke endpoint OpenAI-compatible di `LLM_BASE_URL`.

    >>> factory = ModelFactory(Settings(_env_file=None, use_fake_model=True))
    >>> type(factory.create()).__name__
    'FakeModel'
    >>> factory.create("fake") is factory.create()
    True
    """

    def __init__(self, settings: Settings) -> None:
        """Inisialisasi factory.

        Args:
            settings: Konfigurasi service yang sudah divalidasi.

        Raises:
            ModelNotConfiguredError: Jika `settings.default_model` belum terisi, yang hanya
                terjadi jika validasi `Settings` dilewati.
        """
        if settings.default_model is None:
            raise ModelNotConfiguredError("Settings.default_model is not resolved")
        self._settings = settings
        self._default_model = settings.default_model
        self._models: dict[str, BaseChatModel] = {}

    def resolve_name(self, model_name: str | None = None) -> str:
        """Tentukan nama model final untuk request, tanpa membuat model.

        Args:
            model_name: Nama model dari request. `None` berarti `DEFAULT_MODEL`.

        Returns:
            Nama model yang ada di `AVAILABLE_MODELS`.

        Raises:
            UnknownModelError: Jika nama model tidak ada di `AVAILABLE_MODELS`.

        >>> ModelFactory(Settings(_env_file=None, use_fake_model=True)).resolve_name()
        'fake'
        """
        name = self._default_model if model_name is None else model_name
        if name not in self._settings.available_models:
            raise UnknownModelError(name, self._settings.available_models)
        return name

    def create(self, model_name: str | None = None) -> BaseChatModel:
        """Kembalikan chat model untuk `model_name`, dibuat sekali lalu di-reuse.

        Args:
            model_name: Nama model dari request. `None` berarti `DEFAULT_MODEL`.

        Returns:
            Chat model yang siap dipakai agent.

        Raises:
            UnknownModelError: Jika nama model tidak ada di `AVAILABLE_MODELS`.
            ModelNotConfiguredError: Jika `LLM_BASE_URL` atau `LLM_API_KEY` belum diisi untuk
                model non-fake.
        """
        name = self.resolve_name(model_name)
        model = self._models.get(name)
        if model is None:
            model = self._build(name)
            self._models[name] = model
        return model

    def _build(self, model_name: str) -> BaseChatModel:
        """Buat instance model baru tanpa cek allowlist dan tanpa cache."""
        if model_name == FAKE_MODEL_NAME:
            return FakeModel()
        return self._build_openai_compatible(model_name)

    def _build_openai_compatible(self, model_name: str) -> ChatOpenAI:
        """Buat `ChatOpenAI` dengan base URL dan API key dari `Settings`.

        Raises:
            ModelNotConfiguredError: Jika base URL atau API key kosong.
        """
        base_url = self._settings.llm_base_url
        api_key = self._settings.llm_api_key
        # Tanpa nilai eksplisit, SDK openai jatuh ke OPENAI_API_KEY dan api.openai.com.
        if base_url is None or api_key is None:
            raise ModelNotConfiguredError(
                f"Model {model_name!r} needs LLM_BASE_URL and LLM_API_KEY to be set"
            )
        return ChatOpenAI(
            model=model_name,
            base_url=base_url,
            api_key=api_key,
            temperature=DEFAULT_TEMPERATURE,
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=LLM_MAX_RETRIES,
        )


if __name__ == "__main__":
    factory = ModelFactory(Settings(_env_file=None, use_fake_model=True))
    print(factory.create().invoke("Halo").content)
