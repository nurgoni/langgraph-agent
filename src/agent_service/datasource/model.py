"""Model data source: entri registry, status, hasil query, dan exception domain (FR-51).

>>> entry = DataSourceEntry(id="shop", description="Orders", url_env="SHOP_URL")
>>> entry.catalog is None
True
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from agent_service.core.constants import DATA_SOURCE_ID_MAX_LENGTH, DATA_SOURCE_ID_PATTERN

ENV_NAME_PATTERN: Final = r"^[A-Z_][A-Z0-9_]*$"
DESCRIPTION_MAX_LENGTH: Final = 1000

DataSourceId = Annotated[
    str, StringConstraints(pattern=DATA_SOURCE_ID_PATTERN, max_length=DATA_SOURCE_ID_MAX_LENGTH)
]


class DataSourceEntry(BaseModel):
    """Satu entri `DATA_SOURCES_FILE`. DSN dibaca dari env `url_env`, tidak pernah dari file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: DataSourceId
    description: str = Field(min_length=1, max_length=DESCRIPTION_MAX_LENGTH)
    url_env: str = Field(pattern=ENV_NAME_PATTERN)
    # Path file data catalog (F48), relatif terhadap file registry. Belum dibaca di F39.
    catalog: str | None = None


class DataSourceFile(BaseModel):
    """Isi `DATA_SOURCES_FILE`: `{data_sources: [...]}`."""

    model_config = ConfigDict(extra="forbid")

    data_sources: list[DataSourceEntry] = Field(default_factory=list)


@dataclass(frozen=True)
class DataSourceStatus:
    """Status satu data source untuk `GET /datasources` dan `list_data_sources`.

    `error` berisi alasan unavailable yang aman ditampilkan (tanpa DSN atau password).
    """

    id: str
    description: str
    available: bool
    error: str | None = None


@dataclass(frozen=True)
class QueryResult:
    """Hasil satu query: nama kolom, tipe Postgres, dan baris."""

    columns: Sequence[str]
    types: Sequence[str]
    rows: Sequence[tuple[object, ...]]


def as_int(value: object) -> int:
    """Nilai bilangan bulat dari baris hasil query (`count`, `reltuples`).

    >>> as_int(3)
    3

    Raises:
        TypeError: Jika nilai bukan bilangan bulat.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Expected an integer, got {type(value).__name__}")
    return value


def as_strings(value: object) -> tuple[str, ...]:
    """Array teks dari baris hasil query (`ARRAY(...)` nama kolom).

    >>> as_strings(["a", "b"])
    ('a', 'b')
    """
    if not isinstance(value, list | tuple):
        raise TypeError(f"Expected a list, got {type(value).__name__}")
    return tuple(str(item) for item in value)


class DataSourceError(Exception):
    """Error dasar data source. Pesannya aman dikirim ke model."""


class DataSourceNotFoundError(DataSourceError):
    """Data source tidak terdaftar, atau tidak aktif di project run ini."""

    def __init__(self, data_source_id: str) -> None:
        """Inisialisasi error.

        Args:
            data_source_id: ID yang diminta.
        """
        super().__init__(f"Data source {data_source_id!r} is not available in this project")
        self.data_source_id = data_source_id


class DataSourceUnavailableError(DataSourceError):
    """Data source terdaftar, tapi tidak bisa dipakai (env kosong, gagal konek)."""


class QueryRejectedError(DataSourceError):
    """Query ditolak `QueryGuard`: bukan satu `SELECT` read-only."""


class QueryFailedError(DataSourceError):
    """Database menolak atau menghentikan query (error SQL, timeout, izin)."""


class TableNotFoundError(DataSourceError):
    """Tabel yang diminta tidak ada di skema yang bisa dibaca."""
