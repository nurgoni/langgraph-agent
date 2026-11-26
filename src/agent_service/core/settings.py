"""Konfigurasi service yang dibaca dari environment variable dan file `.env`."""

from pathlib import Path
from typing import Annotated, Final, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from agent_service.core.constants import (
    DEFAULT_AGENT_RECURSION_LIMIT,
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_ARTIFACT_MAX_BYTES,
    DEFAULT_CONTEXT_MAX_TOKENS,
    DEFAULT_DATABASE_URL,
    DEFAULT_HOST,
    DEFAULT_JWT_TTL_SECONDS,
    DEFAULT_LLM_MAX_TOKENS,
    DEFAULT_LLM_MAX_TOKENS_PARAM,
    DEFAULT_LOG_LEVEL,
    DEFAULT_PORT,
    DEFAULT_SANDBOX_TIMEOUT_SECONDS,
    DEFAULT_TOOL_MAX_CONSECUTIVE_ERRORS,
    DEFAULT_TOOL_OUTPUT_MAX_TOKENS,
    ENV_FILE,
    ENV_FILE_ENCODING,
    FAKE_MODEL_NAME,
    LIST_SEPARATOR,
    MAX_PORT,
    MAX_SANDBOX_TIMEOUT_SECONDS,
    MIN_AGENT_RECURSION_LIMIT,
    MIN_ARTIFACT_MAX_BYTES,
    MIN_CONTEXT_MAX_TOKENS,
    MIN_JWT_SECRET_LENGTH,
    MIN_JWT_TTL_SECONDS,
    MIN_LLM_MAX_TOKENS,
    MIN_PORT,
    MIN_SANDBOX_TIMEOUT_SECONDS,
    MIN_TOOL_MAX_CONSECUTIVE_ERRORS,
    MIN_TOOL_OUTPUT_MAX_TOKENS,
    POSTGRES_URL_SCHEMES,
    LogLevel,
    MaxTokensParam,
)

REQUIRED_LLM_FIELDS: Final = ("llm_base_url", "llm_api_key", "default_model")


class Settings(BaseSettings):
    """Konfigurasi service. Satu field = satu env var (nama field dalam huruf besar).

    Tidak ada instance global: buat `Settings()` di lifespan/factory, lalu inject.
    Setelah validasi, `default_model` selalu terisi dan selalu ada di `available_models`.

    Raises:
        pydantic.ValidationError: Jika konfigurasi LLM tidak lengkap (dan `USE_FAKE_MODEL`
            tidak aktif), `DEFAULT_MODEL` tidak ada di allowlist, atau nilai env tidak valid.

    >>> settings = Settings(_env_file=None, use_fake_model=True, jwt_secret="x" * 32)
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
    llm_max_tokens: int = Field(default=DEFAULT_LLM_MAX_TOKENS, ge=MIN_LLM_MAX_TOKENS)
    llm_max_tokens_param: MaxTokensParam = DEFAULT_LLM_MAX_TOKENS_PARAM
    # Anggaran token riwayat + ringkasan yang dikirim ke model per panggilan (FR-39).
    context_max_tokens: int = Field(default=DEFAULT_CONTEXT_MAX_TOKENS, ge=MIN_CONTEXT_MAX_TOKENS)

    # Secret karena berisi password. Default = Postgres dari compose.yaml untuk dev lokal.
    database_url: SecretStr = SecretStr(DEFAULT_DATABASE_URL)

    # File artifact (FR-46). Metadata di Postgres, isi file di direktori ini (volume di compose).
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR
    artifact_max_bytes: int = Field(default=DEFAULT_ARTIFACT_MAX_BYTES, ge=MIN_ARTIFACT_MAX_BYTES)
    # Output tool yang lebih besar ditulis ke workspace thread, model menerima cuplikan (FR-48).
    tool_output_max_tokens: int = Field(
        default=DEFAULT_TOOL_OUTPUT_MAX_TOKENS, ge=MIN_TOOL_OUTPUT_MAX_TOKENS
    )
    # Batas langkah graph per run dan kegagalan beruntun per tool (FR-59).
    agent_recursion_limit: int = Field(
        default=DEFAULT_AGENT_RECURSION_LIMIT, ge=MIN_AGENT_RECURSION_LIMIT
    )
    tool_max_consecutive_errors: int = Field(
        default=DEFAULT_TOOL_MAX_CONSECUTIVE_ERRORS, ge=MIN_TOOL_MAX_CONSECUTIVE_ERRORS
    )

    # Sandbox eksekusi kode (FR-49): URL service `sandbox-runner` dan token bersamanya. Kosong
    # berarti tool `run_python`/`run_shell` tidak di-bind ke agent.
    sandbox_url: str | None = None
    sandbox_token: SecretStr | None = None
    sandbox_timeout_seconds: int = Field(
        default=DEFAULT_SANDBOX_TIMEOUT_SECONDS,
        ge=MIN_SANDBOX_TIMEOUT_SECONDS,
        le=MAX_SANDBOX_TIMEOUT_SECONDS,
    )

    # Kosong berarti tool web search menjawab "not configured", tanpa menggagalkan startup.
    firecrawl_api_key: SecretStr | None = None

    # Wajib (keputusan user): tidak ada mode tanpa auth. Dipakai menandatangani access token.
    jwt_secret: SecretStr = Field(min_length=MIN_JWT_SECRET_LENGTH)
    jwt_ttl_seconds: int = Field(default=DEFAULT_JWT_TTL_SECONDS, ge=MIN_JWT_TTL_SECONDS)
    # Kosong berarti tidak ada origin browser lain yang diizinkan (FR-34).
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    host: str = DEFAULT_HOST
    port: int = Field(default=DEFAULT_PORT, ge=MIN_PORT, le=MAX_PORT)
    log_level: LogLevel = DEFAULT_LOG_LEVEL

    @field_validator("available_models", "cors_origins", mode="before")
    @classmethod
    def _split_comma_list(cls, value: object) -> object:
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
        for raw_name in value.split(LIST_SEPARATOR):
            name = raw_name.strip()
            if name:
                names.append(name)
        return names

    @field_validator("database_url")
    @classmethod
    def _require_postgres_url(cls, value: SecretStr) -> SecretStr:
        """Tolak `DATABASE_URL` selain Postgres, misalnya `sqlite://` sisa konfigurasi lama.

        Args:
            value: URL database yang sudah dibungkus `SecretStr`.

        Returns:
            Nilai yang sama jika skemanya `postgresql://` atau `postgres://`.

        Raises:
            ValueError: Jika skema URL bukan Postgres.
        """
        scheme = urlsplit(value.get_secret_value()).scheme
        if scheme not in POSTGRES_URL_SCHEMES:
            raise ValueError(f"DATABASE_URL must start with postgresql:// (got scheme {scheme!r})")
        return value

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

    @model_validator(mode="after")
    def _require_sandbox_token(self) -> Self:
        """`SANDBOX_URL` tanpa `SANDBOX_TOKEN` ditolak, supaya runner tidak dipanggil tanpa token.

        Raises:
            ValueError: Jika `SANDBOX_URL` terisi tetapi `SANDBOX_TOKEN` kosong.
        """
        if self.sandbox_url is not None and self.sandbox_token is None:
            raise ValueError("SANDBOX_TOKEN is required when SANDBOX_URL is set")
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
    print(Settings(_env_file=None, use_fake_model=True, jwt_secret="x" * 32))
