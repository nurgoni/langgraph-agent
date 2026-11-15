"""Entrypoint: `uv run python -m agent_service.run_migrate` menyiapkan skema Postgres.

Dijalankan oleh service compose `migrate` sebelum service API start (ADR 0001).
"""

import asyncio

from agent_service.core.logging_config import configure_logging
from agent_service.core.settings import Settings
from agent_service.memory.migrator import upgrade_database


def main() -> None:
    """Baca `Settings`, pasang logging, lalu migrasikan database di `DATABASE_URL`.

    Function, bukan class: entrypoint CLI (AGENTS.md § Class vs Function).

    Raises:
        pydantic.ValidationError: Jika env tidak valid.
        psycopg.OperationalError: Jika Postgres tidak bisa dihubungi.
    """
    settings = Settings()
    configure_logging(settings.log_level)
    # SelectorEventLoop: psycopg async tidak bisa memakai ProactorEventLoop (default Windows).
    asyncio.run(
        upgrade_database(settings.database_url.get_secret_value()),
        loop_factory=asyncio.SelectorEventLoop,
    )


if __name__ == "__main__":
    main()
