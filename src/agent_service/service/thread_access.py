"""Cek kepemilikan thread berdasarkan metadata checkpoint.

Setiap run menyimpan `user_id` dan `agent_id` di `RunnableConfig["metadata"]`, dan LangGraph
menyalinnya ke metadata checkpoint. Thread milik user atau agent lain diperlakukan sebagai tidak
ada (404), supaya keberadaannya tidak bocor.
"""

from collections.abc import Mapping
from typing import Final

from langgraph.types import StateSnapshot

USER_ID_METADATA_KEY: Final = "user_id"
AGENT_ID_METADATA_KEY: Final = "agent_id"


class ThreadNotFoundError(Exception):
    """Thread tidak ada, atau bukan milik user/agent yang meminta (HTTP 404).

    >>> str(ThreadNotFoundError("t1"))
    "Thread 't1' not found"
    """

    def __init__(self, thread_id: str) -> None:
        """Inisialisasi error.

        Args:
            thread_id: ID thread yang diminta.
        """
        super().__init__(f"Thread {thread_id!r} not found")
        self.thread_id = thread_id


def run_metadata(user_id: str, agent_id: str) -> dict[str, str]:
    """Metadata yang wajib ikut di setiap run agar kepemilikan thread bisa dicek.

    >>> run_metadata("u1", "chatbot")
    {'user_id': 'u1', 'agent_id': 'chatbot'}
    """
    return {USER_ID_METADATA_KEY: user_id, AGENT_ID_METADATA_KEY: agent_id}


def is_new_thread(snapshot: StateSnapshot) -> bool:
    """Thread belum punya checkpoint sama sekali."""
    return snapshot.metadata is None


def is_thread_owner(metadata: Mapping[str, object], user_id: str, agent_id: str) -> bool:
    """Metadata checkpoint menunjukkan thread dibuat oleh `user_id` lewat `agent_id`.

    >>> is_thread_owner(run_metadata("u1", "chatbot"), "u1", "chatbot")
    True
    >>> is_thread_owner(run_metadata("u1", "chatbot"), "u2", "chatbot")
    False
    """
    return (
        metadata.get(USER_ID_METADATA_KEY) == user_id
        and metadata.get(AGENT_ID_METADATA_KEY) == agent_id
    )


def ensure_thread_owner(
    metadata: Mapping[str, object] | None, thread_id: str, user_id: str, agent_id: str
) -> None:
    """Pastikan thread ada dan dibuat oleh `user_id` lewat `agent_id`.

    Args:
        metadata: Metadata checkpoint terakhir thread (dari `aget_state` atau `aget_tuple`),
            atau `None` jika thread belum punya checkpoint.
        thread_id: ID thread, untuk pesan error.
        user_id: User yang meminta.
        agent_id: Agent di URL request.

    Raises:
        ThreadNotFoundError: Jika thread belum ada, atau metadata-nya milik user/agent lain.
    """
    if metadata is None or not is_thread_owner(metadata, user_id, agent_id):
        raise ThreadNotFoundError(thread_id)
