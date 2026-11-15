"""Endpoint `/health`, selalu tanpa auth (FR-10).

Docstring route menjadi deskripsi di kontrak OpenAPI, jadi contoh pemanggilan ditaruh di sini.

>>> import asyncio
>>> asyncio.run(health())
HealthStatus(status='ok')
"""

from fastapi import APIRouter

from agent_service.schema.responses import HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> HealthStatus:
    """Tanda service hidup. Tidak menyentuh agent atau database."""
    return HealthStatus()
