"""Endpoint `/memories`: user melihat dan menghapus long-term memory miliknya (FR-40, NFR-9).

Setiap route hanya membaca namespace user dari access token. Memory milik user lain tidak bisa
dibaca atau dihapus, dan ID-nya dijawab 404 seperti ID yang tidak ada.
"""

from fastapi import APIRouter, status

from agent_service.memory.user_memories import MemoryRecord
from agent_service.schema.memories import Memory, MemoryList
from agent_service.service.dependencies import MemoryRepositoryDep, PrincipalDep

router = APIRouter(prefix="/memories", tags=["memories"])


def memory_response(record: MemoryRecord) -> Memory:
    """Ubah record repository menjadi schema API."""
    return Memory(
        id=record.memory_id,
        text=record.text,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("")
async def list_memories(principal: PrincipalDep, memories: MemoryRepositoryDep) -> MemoryList:
    """Semua memory milik user, yang terakhir diubah lebih dulu."""
    records = await memories.list_memories(principal.user_id)
    return MemoryList(memories=[memory_response(record) for record in records])


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: str, principal: PrincipalDep, memories: MemoryRepositoryDep
) -> None:
    """Hapus satu memory. Memory yang tidak ada atau milik user lain → 404."""
    await memories.delete(principal.user_id, memory_id)
