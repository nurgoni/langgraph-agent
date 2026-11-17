"""Konfigurasi runner eval, dibaca dari environment variable dan file `.env`.

Eval tidak boleh meng-import `core/`, jadi punya `Settings` sendiri, seperti UI. `AGENT_URL`
dipakai bersama dengan UI.
"""

from pathlib import Path
from typing import Final

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE: Final = Path(".env")
ENV_FILE_ENCODING: Final = "utf-8"
DEFAULT_AGENT_URL: Final = "http://localhost:8080"
# Model lokal bisa berpikir lebih dari satu menit untuk satu kasus.
DEFAULT_EVAL_TIMEOUT_SECONDS: Final = 300.0


class EvalSettings(BaseSettings):
    """Konfigurasi eval. Satu field = satu env var (nama field dalam huruf besar).

    Akun eval sebaiknya service account (`manage create-user <nama> --role service`).

    >>> settings = EvalSettings(_env_file=None, eval_username="evals", eval_password="secret")
    >>> settings.agent_url, settings.eval_password.get_secret_value()
    ('http://localhost:8080', 'secret')
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding=ENV_FILE_ENCODING,
        env_ignore_empty=True,
        extra="ignore",
    )

    agent_url: str = DEFAULT_AGENT_URL
    eval_username: str | None = None
    eval_password: SecretStr | None = None
    eval_timeout_seconds: float = Field(default=DEFAULT_EVAL_TIMEOUT_SECONDS, gt=0)
