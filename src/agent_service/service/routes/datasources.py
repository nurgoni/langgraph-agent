"""Endpoint `/datasources` (read-only): data source yang bisa dipilih project (FR-51).

Data source didefinisikan operator di `DATA_SOURCES_FILE`, bukan lewat API. Alamat dan kredensial
database tidak pernah dikembalikan.
"""

from fastapi import APIRouter

from agent_service.schema.datasources import DataSource, DataSourceList
from agent_service.service.dependencies import DataSourceRegistryDep

router = APIRouter(prefix="/datasources", tags=["datasources"])


@router.get("")
async def list_data_sources(registry: DataSourceRegistryDep) -> DataSourceList:
    """Semua data source terdaftar beserta statusnya, urut sesuai `DATA_SOURCES_FILE`."""
    statuses = registry.statuses()
    return DataSourceList(
        data_sources=[
            DataSource(
                id=status.id,
                description=status.description,
                available=status.available,
                error=status.error,
            )
            for status in statuses
        ]
    )
