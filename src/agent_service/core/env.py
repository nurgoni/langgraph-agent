"""Pembaca env var yang namanya baru diketahui saat runtime, misalnya DSN data source (F39).

`Settings` hanya mengenal env var yang namanya tetap. Registry data source menyebut nama env var
DSN di file (`url_env`), jadi nilainya dibaca lewat `EnvReader`: env proses lebih dulu, lalu file
`.env`, sama seperti urutan prioritas `Settings`.
"""

import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values

from agent_service.core.constants import ENV_FILE, ENV_FILE_ENCODING


class EnvReader:
    """Membaca env var berdasarkan nama. Nilai kosong dianggap tidak diisi (`env_ignore_empty`).

    >>> reader = EnvReader(environ={"SHOP_URL": "postgresql://x"}, env_file=None)
    >>> reader.get("SHOP_URL"), reader.get("MISSING")
    ('postgresql://x', None)
    """

    def __init__(
        self, environ: Mapping[str, str] | None = None, env_file: Path | None = ENV_FILE
    ) -> None:
        """Inisialisasi reader. File `.env` dibaca sekali di sini.

        Args:
            environ: Env proses. Default: `os.environ`.
            env_file: File `.env`. `None` atau file yang tidak ada berarti hanya env proses.
        """
        self._environ = os.environ if environ is None else environ
        self._file_values: dict[str, str] = {}
        if env_file is not None and env_file.is_file():
            for name, value in dotenv_values(env_file, encoding=ENV_FILE_ENCODING).items():
                if value:
                    self._file_values[name] = value

    def get(self, name: str) -> str | None:
        """Nilai env var `name`, atau `None` jika kosong atau tidak ada."""
        value = self._environ.get(name)
        if value:
            return value
        return self._file_values.get(name)


if __name__ == "__main__":
    print(EnvReader().get("DATABASE_URL") is not None)
