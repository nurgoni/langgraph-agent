"""Repository long-term memory per user di atas store LangGraph (FR-40, NFR-9).

Setiap user punya namespace sendiri, `("users", user_id, "memories")`. Semua method menerima
`user_id`, jadi memory user lain tidak pernah terbaca: prefix namespace dicocokkan per elemen.
Repository ini tidak memeriksa persetujuan user; persetujuan diminta tool `save_memory` (harness)
sebelum memanggil `save`.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from langgraph.store.base import BaseStore, Item

USERS_NAMESPACE: Final = "users"
MEMORIES_NAMESPACE: Final = "memories"
TEXT_FIELD: Final = "text"
# Batas jumlah memory per user. Pencarian teks berjalan di Python atas seluruh memory user,
# jadi jumlahnya dijaga kecil sampai ada index embedding (F43).
MAX_MEMORIES_PER_USER: Final = 200
MEMORY_TEXT_MAX_CHARS: Final = 500
# Namespace uuid5 tetap: teks yang sama menghasilkan ID yang sama. Tool yang dijalankan ulang
# saat interrupt dilanjutkan (ToolNode mengulang semua tool call) tidak membuat duplikat.
MEMORY_ID_NAMESPACE: Final = uuid.UUID("6f1c7a52-3d0e-4b8f-9a51-2c9e4d7b8a30")
KEYWORD_PATTERN: Final = re.compile(r"\w+")
# Kata pendek ("is", "my", "di") hampir selalu cocok, jadi tidak dipakai sebagai kata kunci.
MIN_KEYWORD_LENGTH: Final = 3


class InvalidMemoryError(ValueError):
    """Teks memory kosong atau melebihi `MEMORY_TEXT_MAX_CHARS`."""


class MemoryLimitError(ValueError):
    """User sudah punya `MAX_MEMORIES_PER_USER` memory."""


class MemoryNotFoundError(LookupError):
    """User tidak punya memory dengan ID ini (termasuk memory milik user lain, NFR-9)."""

    def __init__(self, memory_id: str) -> None:
        """Inisialisasi error dengan pesan yang tidak membocorkan pemilik memory."""
        super().__init__(f"Memory {memory_id!r} not found")


@dataclass(frozen=True)
class MemoryRecord:
    """Satu memory milik user."""

    memory_id: str
    text: str
    created_at: datetime
    updated_at: datetime


def memory_namespace(user_id: str) -> tuple[str, str, str]:
    """Namespace store milik satu user.

    >>> memory_namespace("user-1")
    ('users', 'user-1', 'memories')
    """
    return (USERS_NAMESPACE, user_id, MEMORIES_NAMESPACE)


def normalize_memory_text(text: str) -> str:
    """Rapikan spasi, lalu validasi panjangnya.

    >>> normalize_memory_text("  User   prefers short answers ")
    'User prefers short answers'

    Raises:
        InvalidMemoryError: Jika teks kosong atau lebih dari `MEMORY_TEXT_MAX_CHARS`.
    """
    normalized = " ".join(text.split())
    if not normalized:
        raise InvalidMemoryError("Memory text is empty")
    if len(normalized) > MEMORY_TEXT_MAX_CHARS:
        raise InvalidMemoryError(
            f"Memory text is {len(normalized)} characters, the limit is {MEMORY_TEXT_MAX_CHARS}"
        )
    return normalized


def memory_id_for(text: str) -> str:
    """ID deterministik dari teks yang sudah dinormalisasi, tanpa membedakan huruf besar-kecil.

    >>> memory_id_for("Likes tea") == memory_id_for("likes TEA")
    True
    """
    return str(uuid.uuid5(MEMORY_ID_NAMESPACE, text.casefold()))


def keywords_of(query: str) -> set[str]:
    """Kata kunci pencarian: kata huruf kecil dengan panjang minimal `MIN_KEYWORD_LENGTH`.

    >>> sorted(keywords_of("What is my favourite tea?"))
    ['favourite', 'tea', 'what']
    """
    words = KEYWORD_PATTERN.findall(query.casefold())
    return {word for word in words if len(word) >= MIN_KEYWORD_LENGTH}


def keyword_score(text: str, keywords: set[str]) -> int:
    """Jumlah kata kunci yang menjadi awal salah satu kata di teks ("prefer" cocok "prefers").

    >>> keyword_score("User prefers green tea", {"prefer", "tea", "coffee", "ree"})
    2
    """
    words = set(KEYWORD_PATTERN.findall(text.casefold()))
    score = 0
    for keyword in keywords:
        if any(word.startswith(keyword) for word in words):
            score += 1
    return score


class UserMemoryRepository:
    """Baca, simpan, cari, dan hapus memory milik satu user di `BaseStore`."""

    def __init__(self, store: BaseStore) -> None:
        """Inisialisasi repository.

        Args:
            store: Store LangGraph (`AsyncPostgresStore` di service, `InMemoryStore` di test).
        """
        self._store = store

    async def list_memories(
        self, user_id: str, limit: int = MAX_MEMORIES_PER_USER
    ) -> list[MemoryRecord]:
        """Memory user, yang terakhir diubah lebih dulu.

        Args:
            user_id: Pemilik memory (`sub` token).
            limit: Jumlah maksimum memory.
        """
        # Ambil semua lalu urutkan di sini: urutan dan pemotongan `asearch` berbeda antar store
        # (Postgres terbaru dulu, InMemoryStore urut sisip), sedangkan jumlahnya dibatasi.
        namespace = memory_namespace(user_id)
        items = await self._store.asearch(namespace, limit=MAX_MEMORIES_PER_USER)
        records = [_to_record(item) for item in items]
        records.sort(key=lambda record: record.updated_at, reverse=True)
        return records[:limit]

    async def search(self, user_id: str, query: str, limit: int) -> list[MemoryRecord]:
        """Memory yang paling banyak memuat kata dari `query`, lalu yang terbaru.

        Query tanpa kata kunci mengembalikan memory terbaru. Memory tanpa kata yang cocok tidak
        ikut dikembalikan.
        """
        records = await self.list_memories(user_id)
        keywords = keywords_of(query)
        if not keywords:
            return records[:limit]
        scored = [(keyword_score(record.text, keywords), record) for record in records]
        matches = [(score, record) for score, record in scored if score > 0]
        # sort stabil: memory dengan skor sama tetap urut terbaru lebih dulu.
        matches.sort(key=lambda match: match[0], reverse=True)
        return [record for _, record in matches[:limit]]

    async def save(self, user_id: str, text: str) -> MemoryRecord:
        """Simpan memory. Teks yang sama (tanpa beda huruf besar-kecil) memperbarui memory lama.

        Raises:
            InvalidMemoryError: Jika teks kosong atau terlalu panjang.
            MemoryLimitError: Jika memory baru melebihi `MAX_MEMORIES_PER_USER`.
        """
        normalized = normalize_memory_text(text)
        memory_id = memory_id_for(normalized)
        namespace = memory_namespace(user_id)
        existing = await self._store.aget(namespace, memory_id)
        if existing is None and len(await self.list_memories(user_id)) >= MAX_MEMORIES_PER_USER:
            raise MemoryLimitError(
                f"User already has {MAX_MEMORIES_PER_USER} memories. Delete some first."
            )
        await self._store.aput(namespace, memory_id, {TEXT_FIELD: normalized})
        saved = await self._store.aget(namespace, memory_id)
        if saved is None:
            raise RuntimeError(f"Memory {memory_id} was not stored")
        return _to_record(saved)

    async def delete(self, user_id: str, memory_id: str) -> None:
        """Hapus memory milik user.

        Raises:
            MemoryNotFoundError: Jika user tidak punya memory dengan ID itu.
        """
        namespace = memory_namespace(user_id)
        if await self._store.aget(namespace, memory_id) is None:
            raise MemoryNotFoundError(memory_id)
        await self._store.adelete(namespace, memory_id)


def _to_record(item: Item) -> MemoryRecord:
    """Item store menjadi `MemoryRecord`."""
    return MemoryRecord(
        memory_id=item.key,
        text=str(item.value.get(TEXT_FIELD, "")),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


if __name__ == "__main__":
    import asyncio

    from langgraph.store.memory import InMemoryStore

    async def _demo() -> None:
        repository = UserMemoryRepository(InMemoryStore())
        await repository.save("user-1", "User prefers answers in Indonesian")
        await repository.save("user-1", "User works as a data analyst")
        print(await repository.search("user-1", "what language do I prefer?", limit=3))
        print(await repository.list_memories("user-2"))

    asyncio.run(_demo())
