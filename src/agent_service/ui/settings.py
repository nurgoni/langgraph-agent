"""Konfigurasi UI Streamlit, dibaca dari environment variable dan file `.env`.

UI tidak boleh meng-import `core/`, jadi UI punya `Settings` sendiri yang hanya berisi nilai yang
dibutuhkan untuk menghubungi service.
"""

from pathlib import Path
from typing import Final

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE: Final = Path(".env")
ENV_FILE_ENCODING: Final = "utf-8"
DEFAULT_AGENT_URL: Final = "http://localhost:8080"
DEFAULT_REQUEST_TIMEOUT_SECONDS: Final = 120.0


class UiSettings(BaseSettings):
    """Konfigurasi UI. Satu field = satu env var (nama field dalam huruf besar).

    `.env` dipakai bersama dengan service, jadi variabel milik service diabaikan.

    >>> settings = UiSettings(_env_file=None, agent_url="http://agent:8080")
    >>> settings.agent_url, settings.auth_secret
    ('http://agent:8080', None)
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding=ENV_FILE_ENCODING,
        env_ignore_empty=True,
        extra="ignore",
    )

    agent_url: str = DEFAULT_AGENT_URL
    auth_secret: SecretStr | None = None
    request_timeout_seconds: float = Field(default=DEFAULT_REQUEST_TIMEOUT_SECONDS, gt=0)

    def auth_token(self) -> str | None:
        """Token bearer dalam bentuk teks, atau `None` jika service tanpa auth."""
        if self.auth_secret is None:
            return None
        return self.auth_secret.get_secret_value()
