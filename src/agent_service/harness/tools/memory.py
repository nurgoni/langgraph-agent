"""Tool `search_memory` dan `save_memory`: long-term memory user (FR-40, ADR 0002).

`save_memory` meminta persetujuan user lewat `interrupt()` (pola F16) sebelum menyimpan. Jawaban
user datang sebagai teks pesan berikutnya (keputusan user F30): jawaban "ya" menyimpan, jawaban
lain menolak dan diteruskan ke model supaya model bisa menanggapinya.

Saat graph dilanjutkan, `ToolNode` menjalankan ulang semua tool call di giliran itu. Penyimpanan
ulang aman karena ID memory diturunkan dari teksnya (`memory_id_for`).
"""

import re
from collections.abc import Mapping
from typing import Any, Final

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, ToolException, tool
from langgraph.types import interrupt

from agent_service.core.constants import USER_ID_CONFIG_KEY
from agent_service.memory.user_memories import (
    InvalidMemoryError,
    MemoryLimitError,
    MemoryRecord,
    UserMemoryRepository,
    normalize_memory_text,
)

SEARCH_MEMORY_TOOL_NAME: Final = "search_memory"
SAVE_MEMORY_TOOL_NAME: Final = "save_memory"
CONFIGURABLE_KEY: Final = "configurable"
SEARCH_RESULT_LIMIT: Final = 5

# Teks yang dilihat user (pertanyaan interrupt) berbahasa Inggris, sama seperti teks UI lain.
APPROVAL_QUESTION: Final = (
    'Save this to memory for future conversations?\n\n"{memory}"\n\n'
    'Reply "yes" to save it, or anything else to skip.'
)
# Jawaban dianggap setuju jika diawali kata setuju dan semua katanya ada di daftar, jadi
# "ya, tapi ganti jadi X" adalah penolakan yang diteruskan ke model.
APPROVAL_LEAD_WORDS: Final = frozenset(
    {"y", "yes", "yeah", "yep", "ok", "okay", "sure", "save", "approve", "approved"}
    | {"ya", "iya", "oke", "boleh", "setuju", "simpan", "silakan"}
)
APPROVAL_FILLER_WORDS: Final = frozenset(
    {"please", "it", "do", "go", "ahead", "saja", "aja", "dong", "tolong"}
)
WORD_PATTERN: Final = re.compile(r"\w+")
SAVED_TEXT: Final = 'Saved to memory: "{memory}"'
DECLINED_TEXT: Final = (
    "The user did not approve saving this memory, so nothing was saved. Their reply: "
    '"{reply}". Respond to their reply.'
)
NO_MATCHES_TEXT: Final = "No saved memories match this query."
MEMORY_UNAVAILABLE_TEXT: Final = "Memory is not available in this conversation."


def memory_user_id(config: Mapping[str, Any] | None) -> str | None:  # Any: RunnableConfig
    """Pemilik run dari `configurable`, atau `None` jika run tidak punya user.

    >>> memory_user_id({"configurable": {"user_id": "user-1"}})
    'user-1'
    >>> memory_user_id({}) is None
    True
    """
    configurable = (config or {}).get(CONFIGURABLE_KEY) or {}
    user_id = configurable.get(USER_ID_CONFIG_KEY)
    if not isinstance(user_id, str) or not user_id:
        return None
    return user_id


def is_approval(reply: object) -> bool:
    """Cek apakah jawaban user menyetujui penyimpanan.

    >>> is_approval("Yes!"), is_approval("ya, simpan saja"), is_approval("ok go ahead")
    (True, True, True)
    >>> is_approval("no"), is_approval("ya tapi ganti jadi kopi"), is_approval("please")
    (False, False, False)
    """
    if not isinstance(reply, str):
        return False
    words = WORD_PATTERN.findall(reply.casefold())
    if not words or words[0] not in APPROVAL_LEAD_WORDS:
        return False
    allowed = APPROVAL_LEAD_WORDS | APPROVAL_FILLER_WORDS
    return all(word in allowed for word in words)


def render_memories(records: list[MemoryRecord]) -> str:
    """Memory sebagai daftar berpoin.

    >>> from datetime import datetime
    >>> now = datetime(2026, 11, 17)
    >>> print(render_memories([MemoryRecord("m1", "Likes tea", now, now)]))
    - Likes tea
    """
    return "\n".join(f"- {record.text}" for record in records)


def create_memory_tools(repository: UserMemoryRepository) -> list[BaseTool]:
    """Buat tool `search_memory` dan `save_memory` yang terikat pada `repository`.

    Function, bukan class: factory `@tool` (AGENTS.md § Class vs Function). User dibaca dari
    config setiap pemanggilan, jadi satu tool dipakai semua user.
    """

    @tool(SEARCH_MEMORY_TOOL_NAME)
    async def search_memory(query: str, config: RunnableConfig) -> str:
        """Search facts about the user that were saved in earlier conversations.

        Your most recent memories are already listed under "Memory" in your instructions. Use
        this to look for older ones, for example when the user asks what you remember about a
        topic.

        Args:
            query: Words to look for, for example "favourite food" or "job".
        """
        user_id = _require_user(config)
        records = await repository.search(user_id, query, SEARCH_RESULT_LIMIT)
        if not records:
            return NO_MATCHES_TEXT
        return render_memories(records)

    @tool(SAVE_MEMORY_TOOL_NAME)
    async def save_memory(memory: str, config: RunnableConfig) -> str:
        """Save one lasting fact or preference about the user for future conversations.

        Only call this when the user asks you to remember something, or shares something that
        will matter later (their name, role, preferences). The user is asked to approve before
        anything is saved. Call it at most once per turn and combine related facts.

        Args:
            memory: One short sentence about the user, for example "User prefers answers in
                Indonesian".
        """
        user_id = _require_user(config)
        try:
            text = normalize_memory_text(memory)
        except InvalidMemoryError as error:
            raise ToolException(str(error)) from error
        reply = interrupt(APPROVAL_QUESTION.format(memory=text))
        if not is_approval(reply):
            return DECLINED_TEXT.format(reply=reply)
        try:
            await repository.save(user_id, text)
        except MemoryLimitError as error:
            raise ToolException(str(error)) from error
        return SAVED_TEXT.format(memory=text)

    return [search_memory, save_memory]


def _require_user(config: RunnableConfig) -> str:
    """User pemilik run.

    Raises:
        ToolException: Jika run tidak punya user (misalnya dijalankan tanpa service).
    """
    user_id = memory_user_id(config)
    if user_id is None:
        raise ToolException(MEMORY_UNAVAILABLE_TEXT)
    return user_id
