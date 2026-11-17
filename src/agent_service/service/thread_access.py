"""Cek kepemilikan thread berdasarkan metadata checkpoint.

Setiap run menyimpan `user_id`, `agent_id`, dan (untuk thread di dalam project) `project_id` di
`RunnableConfig["metadata"]`, dan LangGraph menyalinnya ke metadata checkpoint. Thread milik user,
agent, atau project lain diperlakukan sebagai tidak ada (404), supaya keberadaannya tidak bocor.
Thread project tidak bisa dibuka lewat route agent, dan sebaliknya.
"""

from collections.abc import Mapping
from typing import Final

from langgraph.types import StateSnapshot

USER_ID_METADATA_KEY: Final = "user_id"
AGENT_ID_METADATA_KEY: Final = "agent_id"
PROJECT_ID_METADATA_KEY: Final = "project_id"


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


def run_metadata(user_id: str, agent_id: str, project_id: str | None = None) -> dict[str, str]:
    """Metadata yang wajib ikut di setiap run agar kepemilikan thread bisa dicek.

    `project_id` hanya ditulis untuk thread di dalam project. Thread tanpa key ini (termasuk thread
    dari sebelum F26) adalah thread tanpa project.

    >>> run_metadata("u1", "chatbot")
    {'user_id': 'u1', 'agent_id': 'chatbot'}
    >>> run_metadata("u1", "chatbot", "p1")
    {'user_id': 'u1', 'agent_id': 'chatbot', 'project_id': 'p1'}
    """
    metadata = {USER_ID_METADATA_KEY: user_id, AGENT_ID_METADATA_KEY: agent_id}
    if project_id is not None:
        metadata[PROJECT_ID_METADATA_KEY] = project_id
    return metadata


def is_new_thread(snapshot: StateSnapshot) -> bool:
    """Thread belum punya checkpoint sama sekali."""
    return snapshot.metadata is None


def is_thread_owner(
    metadata: Mapping[str, object], user_id: str, agent_id: str, project_id: str | None = None
) -> bool:
    """Metadata checkpoint menunjukkan thread dibuat oleh `user_id` lewat `agent_id` di project ini.

    >>> is_thread_owner(run_metadata("u1", "chatbot"), "u1", "chatbot")
    True
    >>> is_thread_owner(run_metadata("u1", "chatbot"), "u2", "chatbot")
    False
    >>> is_thread_owner(run_metadata("u1", "chatbot", "p1"), "u1", "chatbot")
    False
    """
    return (
        metadata.get(USER_ID_METADATA_KEY) == user_id
        and metadata.get(AGENT_ID_METADATA_KEY) == agent_id
        and metadata.get(PROJECT_ID_METADATA_KEY) == project_id
    )


def ensure_thread_owner(
    metadata: Mapping[str, object] | None,
    thread_id: str,
    user_id: str,
    agent_id: str,
    project_id: str | None = None,
) -> None:
    """Pastikan thread ada dan dibuat oleh `user_id` lewat `agent_id`, di `project_id` ini.

    Args:
        metadata: Metadata checkpoint terakhir thread (dari `aget_state` atau `aget_tuple`),
            atau `None` jika thread belum punya checkpoint.
        thread_id: ID thread, untuk pesan error.
        user_id: User yang meminta.
        agent_id: Agent di URL request, atau agent dasar project.
        project_id: Project di URL request, atau `None` untuk route agent.

    Raises:
        ThreadNotFoundError: Jika thread belum ada, atau metadata-nya milik user, agent, atau
            project lain.
    """
    if metadata is None or not is_thread_owner(metadata, user_id, agent_id, project_id):
        raise ThreadNotFoundError(thread_id)
