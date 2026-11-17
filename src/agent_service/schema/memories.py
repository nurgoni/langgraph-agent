"""Model response long-term memory user (FR-40).

Memory dibuat oleh agent lewat tool `save_memory` setelah user menyetujui, jadi API hanya
menyediakan daftar dan hapus.

>>> from datetime import datetime, timezone
>>> now = datetime(2026, 11, 17, tzinfo=timezone.utc)
>>> MemoryList(memories=[Memory(id="m1", text="Likes tea", created_at=now, updated_at=now)])
MemoryList(memories=[Memory(id='m1', text='Likes tea', ...)])
"""

from datetime import datetime

from pydantic import BaseModel, Field


class Memory(BaseModel):
    """Satu fakta tentang user yang disimpan dengan persetujuannya."""

    id: str = Field(description="Memory ID, used to delete it.")
    text: str = Field(examples=["User prefers answers in Indonesian"])
    created_at: datetime
    updated_at: datetime


class MemoryList(BaseModel):
    """Isi `GET /memories`: memory milik user, yang terakhir diubah lebih dulu."""

    memories: list[Memory]
