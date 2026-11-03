"""Konstanta bernama yang dipakai lintas layer.

Setiap literal yang punya makna ditaruh di sini, bukan diulang inline.

>>> DEFAULT_PORT
8080
>>> MIN_PORT <= DEFAULT_PORT <= MAX_PORT
True
"""

from pathlib import Path
from typing import Final, Literal

ENV_FILE: Final = Path(".env")
ENV_FILE_ENCODING: Final = "utf-8"

DEFAULT_HOST: Final = "0.0.0.0"
DEFAULT_PORT: Final = 8080
MIN_PORT: Final = 1
MAX_PORT: Final = 65535

DEFAULT_SQLITE_DB_PATH: Final = Path("checkpoints.db")

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
DEFAULT_LOG_LEVEL: Final[LogLevel] = "INFO"

FAKE_MODEL_NAME: Final = "fake"
MODEL_LIST_SEPARATOR: Final = ","
