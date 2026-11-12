"""Konfigurasi service yang dibaca dari environment variable dan file `.env`."""

from pathlib import Path
from typing import Annotated, Final, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from agent_service.core.constants import (
    DEFAULT_HOST,
    DEFAULT_LOG_LEVEL,
    DEFAULT_PORT,
    DEFAULT_SQLITE_DB_PATH,
    ENV_FILE,
    ENV_FILE_ENCODING,
    FAKE_MODEL_NAME,
    MAX_PORT,
    MIN_PORT,
    MODEL_LIST_SEPARATOR,
    LogLevel,
)

REQUIRED_LLM_FIELDS: Final = ("llm_base_url", "llm_api_key", "default_model")


class Settings(BaseSettings):
    """Konfigurasi service. Satu field = satu env var (nama field dalam huruf besar).

    Tidak ada instance global: buat `Settings()` di lifespan/factory, lalu inject.
    Setelah validasi, `default_model` selalu terisi dan selalu ada di `available_models`.

    Raises:
        pydantic.ValidationError: Jika konfigurasi LLM tidak lengkap (dan `USE_FAKE_MODEL`
            tidak aktif), `DEFAULT_MODEL` tidak ada di allowlist, atau nilai env tidak valid.

    >>> settings = Settings(_env_file=None, use_fake_model=True)
    >>> settings.default_model, settings.available_models
    ('fake', ['fake'])
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding=ENV_FILE_ENCODING,
        env_ignore_empty=True,
        extra="ignore",
    )

    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    default_model: str | None = None
    # NoDecode: nilai env dibiarkan string agar dipisah koma, bukan di-parse sebagai JSON.
    available_models: Annotated[list[str], NoDecode] = Field(default_factory=list)
    use_fake_model: bool = False

    sqlite_db_path: Path = DEFAULT_SQLITE_DB_PATH

    # Kosong berarti tool web search menjawab "not configured", tanpa menggagalkan startup.
    firecrawl_api_key: SecretStr | None = None

    auth_secret: SecretStr | None = None
    host: str = DEFAULT_HOST
    port: int = Field(default=DEFAULT_PORT, ge=MIN_PORT, le=MAX_PORT)
    log_level: LogLevel = DEFAULT_LOG_LEVEL

    @field_validator("available_models", mode="before")
    @classmethod
    def _split_model_list(cls, value: object) -> object:
        """Pisahkan string `"a, b"` menjadi `["a", "b"]`.

        Args:
            value: Nilai mentah dari env atau argumen konstruktor.

        Returns:
            List nama model tanpa spasi dan entri kosong, atau `value` apa adanya jika
            bukan string.
        """
        if not isinstance(value, str):
            return value
        names: list[str] = []
        for raw_name in value.split(MODEL_LIST_SEPARATOR):
            name = raw_name.strip()
            if name:
                names.append(name)
        return names

    @model_validator(mode="after")
    def _resolve_models(self) -> Self:
        """Lengkapi dan validasi pilihan model.

        Returns:
            Instance yang sama, dengan `default_model` dan `available_models` final.

        Raises:
            ValueError: Jika konfigurasi LLM kurang atau model default di luar allowlist.
        """
        if not self.use_fake_model:
            self._require_llm_fields()
        # Hanya bisa None di mode fake, karena di mode lain sudah dicek oleh _require_llm_fields.
        default_model = FAKE_MODEL_NAME if self.default_model is None else self.default_model
        self.default_model = default_model
        if not self.available_models:
            self.available_models = [default_model]
        if self.use_fake_model and FAKE_MODEL_NAME not in self.available_models:
            self.available_models.append(FAKE_MODEL_NAME)
        if default_model not in self.available_models:
            raise ValueError(
                f"DEFAULT_MODEL {default_model!r} is not in AVAILABLE_MODELS "
                f"{self.available_models}"
            )
        return self

    def _require_llm_fields(self) -> None:
        """Pastikan semua env LLM wajib terisi.

        Raises:
            ValueError: Berisi daftar env var yang kosong.
        """
        missing = [name.upper() for name in REQUIRED_LLM_FIELDS if getattr(self, name) is None]
        if missing:
            raise ValueError(
                f"Missing LLM configuration: {', '.join(missing)}. "
                "Set them or enable USE_FAKE_MODEL=true."
            )


if __name__ == "__main__":
    print(Settings(_env_file=None, use_fake_model=True))
