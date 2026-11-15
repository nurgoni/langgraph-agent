"""Entrypoint: `uv run python -m agent_service.run_service` menjalankan API dengan uvicorn."""

from typing import Final

import uvicorn

from agent_service.core.logging_config import configure_logging
from agent_service.core.settings import Settings
from agent_service.service.app import create_app

# Import string yang dipakai uvicorn langsung sebagai loop factory. psycopg async tidak bisa
# memakai ProactorEventLoop, loop default uvicorn di Windows. Di Linux, selector sudah default.
UVICORN_SELECTOR_LOOP: Final = "asyncio:SelectorEventLoop"


def main() -> None:
    """Baca `Settings`, pasang logging, lalu jalankan service di `HOST:PORT`.

    Function, bukan class: entrypoint CLI (AGENTS.md § Class vs Function).

    Raises:
        pydantic.ValidationError: Jika env tidak valid, sebelum server mulai listen.
    """
    settings = Settings()
    configure_logging(settings.log_level)
    # log_config=None: uvicorn memakai root logger dari configure_logging, bukan config-nya sendiri.
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_config=None,
        loop=UVICORN_SELECTOR_LOOP,
    )


if __name__ == "__main__":
    main()
