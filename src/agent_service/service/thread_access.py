"""Cek kepemilikan thread berdasarkan metadata checkpoint.

Setiap run menyimpan `user_id` dan `agent_id` di `RunnableConfig["metadata"]`, dan LangGraph
menyalinnya ke metadata checkpoint. Thread milik user atau agent lain diperlakukan sebagai tidak
ada (404), supaya keberadaannya tidak bocor.
"""

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


def ensure_thread_owner(
    snapshot: StateSnapshot, thread_id: str, user_id: str, agent_id: str
) -> None:
    """Pastikan thread ada dan dibuat oleh `user_id` lewat `agent_id`.

    Args:
        snapshot: Hasil `graph.aget_state` untuk thread ini.
        thread_id: ID thread, untuk pesan error.
        user_id: User yang meminta.
        agent_id: Agent di URL request.

    Raises:
        ThreadNotFoundError: Jika thread belum ada, atau metadata-nya milik user/agent lain.
    """
    metadata = snapshot.metadata
    if metadata is None:
        raise ThreadNotFoundError(thread_id)
    if metadata.get(USER_ID_METADATA_KEY) != user_id:
        raise ThreadNotFoundError(thread_id)
    if metadata.get(AGENT_ID_METADATA_KEY) != agent_id:
        raise ThreadNotFoundError(thread_id)
