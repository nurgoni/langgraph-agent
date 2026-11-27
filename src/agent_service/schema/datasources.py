"""Model response data source read-only (FR-51) untuk `GET /datasources`.

>>> DataSource(id="shop", description="Orders", available=True).error is None
True
"""

from typing import Annotated, Final

from pydantic import BaseModel, Field, StringConstraints

# ID data source di `ProjectSettings.data_source_ids`. Sama dengan `core/constants.py`, disalin
# karena schema hanya bergantung pada pydantic (test menjaga keduanya tetap sama).
DATA_SOURCE_ID_PATTERN: Final = r"^[a-z0-9]+([_-][a-z0-9]+)*$"
DATA_SOURCE_ID_MAX_LENGTH: Final = 64

DataSourceId = Annotated[
    str, StringConstraints(pattern=DATA_SOURCE_ID_PATTERN, max_length=DATA_SOURCE_ID_MAX_LENGTH)
]


class DataSource(BaseModel):
    """Satu data source terdaftar. Kredensial dan alamat database tidak pernah ditampilkan."""

    id: str
    description: str
    available: bool = Field(description="False when the service cannot use it right now.")
    error: str | None = Field(default=None, description="Why the data source is unavailable.")


class DataSourceList(BaseModel):
    """Isi `GET /datasources`: semua data source, urut sesuai `DATA_SOURCES_FILE`."""

    data_sources: list[DataSource]
