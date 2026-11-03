"""Endpoint `/health`, selalu tanpa auth (FR-10)."""

from fastapi import APIRouter

from agent_service.schema.responses import HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> HealthStatus:
    """Tanda service hidup. Tidak menyentuh agent atau database.

    >>> import asyncio
    >>> asyncio.run(health())
    HealthStatus(status='ok')
    """
    return HealthStatus()
