"""`DataSourceRegistry`: data source dari `DATA_SOURCES_FILE`, dibuka saat lifespan (FR-51).

Pola `AgentRegistry`: registry dibuat di `create_app` dari file (tanpa koneksi), lalu `open()` di
lifespan. Data source yang env DSN-nya kosong atau gagal konek ditandai unavailable dengan alasan
yang jelas, dan service tetap start. File registry yang tidak ada berarti tanpa data source; file
yang rusak menggagalkan startup, karena itu kesalahan konfigurasi.
"""

import asyncio
import logging
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Final

import yaml
from pydantic import ValidationError

from agent_service.core.env import EnvReader
from agent_service.datasource.model import (
    DataSourceEntry,
    DataSourceFile,
    DataSourceNotFoundError,
    DataSourceStatus,
    DataSourceUnavailableError,
    QueryFailedError,
)
from agent_service.datasource.source import SqlDataSource

logger = logging.getLogger(__name__)

FILE_ENCODING: Final = "utf-8"
NOT_OPENED_TEXT: Final = "The data source has not been opened yet."
CONNECT_FAILED_TEXT: Final = "Cannot connect to the database."
MISSING_ENV_TEMPLATE: Final = "Environment variable {name} is not set."


class InvalidDataSourcesFileError(ValueError):
    """`DATA_SOURCES_FILE` tidak bisa dibaca sebagai YAML registry yang valid."""


def load_entries(path: Path) -> list[DataSourceEntry]:
    """Baca entri registry dari `path`. File yang tidak ada berarti tanpa data source.

    Raises:
        InvalidDataSourcesFileError: YAML rusak, field tidak valid, atau ID ganda.
    """
    if not path.is_file():
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding=FILE_ENCODING)) or {}
        parsed = DataSourceFile.model_validate(raw)
    except (yaml.YAMLError, ValidationError) as error:
        raise InvalidDataSourcesFileError(f"Invalid data sources file {path}: {error}") from error
    ids = [entry.id for entry in parsed.data_sources]
    duplicates = sorted({entry_id for entry_id in ids if ids.count(entry_id) > 1})
    if duplicates:
        raise InvalidDataSourcesFileError(f"Duplicate data source ids in {path}: {duplicates}")
    return parsed.data_sources


class DataSourceRegistry:
    """Data source yang terdaftar beserta statusnya, dipakai tool dan `GET /datasources`."""

    def __init__(
        self,
        entries: Sequence[DataSourceEntry],
        env: EnvReader,
        timeout_seconds: int,
    ) -> None:
        """Inisialisasi registry tanpa membuka koneksi.

        Args:
            entries: Entri dari `load_entries`, urut sesuai file.
            env: Pembaca env untuk DSN (`url_env`).
            timeout_seconds: `statement_timeout` setiap query (`SQL_TIMEOUT_SECONDS`).
        """
        self._entries = list(entries)
        self._env = env
        self._timeout_seconds = timeout_seconds
        self._sources: dict[str, SqlDataSource] = {}
        self._errors: dict[str, str] = {entry.id: NOT_OPENED_TEXT for entry in self._entries}

    @property
    def ids(self) -> list[str]:
        """ID semua data source terdaftar, termasuk yang unavailable."""
        return [entry.id for entry in self._entries]

    def contains(self, data_source_id: str) -> bool:
        """Cek apakah ID terdaftar (untuk validasi `ProjectSettings.data_source_ids`)."""
        return data_source_id in self.ids

    async def open(self) -> None:
        """Buka semua data source secara paralel. Kegagalan hanya menandai unavailable."""
        await asyncio.gather(*(self._open_one(entry) for entry in self._entries))

    async def close(self) -> None:
        """Tutup semua pool yang terbuka."""
        sources = list(self._sources.values())
        self._sources.clear()
        await asyncio.gather(*(source.close() for source in sources))

    def statuses(self, ids: Iterable[str] | None = None) -> list[DataSourceStatus]:
        """Status data source, urut sesuai file. `ids` membatasi ke data source tertentu."""
        wanted = None if ids is None else set(ids)
        statuses: list[DataSourceStatus] = []
        for entry in self._entries:
            if wanted is not None and entry.id not in wanted:
                continue
            error = self._errors.get(entry.id)
            statuses.append(DataSourceStatus(entry.id, entry.description, error is None, error))
        return statuses

    def get(self, data_source_id: str) -> SqlDataSource:
        """Data source yang siap dipakai.

        Raises:
            DataSourceNotFoundError: ID tidak terdaftar.
            DataSourceUnavailableError: Terdaftar tapi tidak terbuka.
        """
        if not self.contains(data_source_id):
            raise DataSourceNotFoundError(data_source_id)
        source = self._sources.get(data_source_id)
        if source is None:
            reason = self._errors.get(data_source_id, NOT_OPENED_TEXT)
            raise DataSourceUnavailableError(
                f"Data source {data_source_id!r} is unavailable: {reason}"
            )
        return source

    async def _open_one(self, entry: DataSourceEntry) -> None:
        """Buka satu data source, atau catat alasan kegagalannya."""
        database_url = self._env.get(entry.url_env)
        if database_url is None:
            self._mark_unavailable(entry.id, MISSING_ENV_TEMPLATE.format(name=entry.url_env))
            return
        source = SqlDataSource(entry.id, database_url, self._timeout_seconds)
        try:
            await source.open()
        except QueryFailedError as error:
            logger.warning("Data source %s cannot connect: %s", entry.id, error)
            await source.close()
            self._mark_unavailable(entry.id, CONNECT_FAILED_TEXT)
            return
        self._sources[entry.id] = source
        self._errors.pop(entry.id, None)
        logger.info("Data source %s is available", entry.id)

    def _mark_unavailable(self, data_source_id: str, reason: str) -> None:
        """Catat alasan data source tidak bisa dipakai."""
        logger.warning("Data source %s is unavailable: %s", data_source_id, reason)
        self._errors[data_source_id] = reason


if __name__ == "__main__":
    registry = DataSourceRegistry(load_entries(Path("datasources.yaml")), EnvReader(), 30)
    print(registry.ids)
