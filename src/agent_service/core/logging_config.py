"""Konfigurasi logging terpusat. Modul lain cukup memakai `logging.getLogger(__name__)`."""

import logging
import sys
from typing import Final, TextIO

from agent_service.core.constants import LogLevel

LOG_FORMAT: Final = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
NOISY_LOGGERS: Final = ("httpx", "httpcore")
NOISY_LOGGER_LEVEL: Final = logging.WARNING


def configure_logging(level: LogLevel, stream: TextIO | None = None) -> None:
    """Pasang satu handler di root logger dengan format standar project.

    Ditulis sebagai function, bukan class, karena hanya satu aksi tanpa state
    (AGENTS.md § Class vs Function). Aman dipanggil berulang karena handler lama diganti.

    Args:
        level: Level minimum root logger, biasanya `Settings.log_level`.
        stream: Tujuan output. Default `sys.stderr`.
    """
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        stream=stream or sys.stderr,
        force=True,
    )
    for logger_name in NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(NOISY_LOGGER_LEVEL)


if __name__ == "__main__":
    configure_logging("DEBUG")
    logging.getLogger(__name__).info("logging configured")
