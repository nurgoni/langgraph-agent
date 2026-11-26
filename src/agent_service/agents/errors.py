"""Exception domain untuk agent. Service memetakannya ke status HTTP (FR-15)."""

from typing import Final

# Pesan untuk client saat run melewati `recursion_limit` (FR-59). Dipakai `/invoke` (HTTP 500) dan
# frame `error` di `/stream`.
STEP_LIMIT_ERROR_DETAIL: Final = (
    "The agent reached its step limit (AGENT_RECURSION_LIMIT) before finishing this request."
)


class AgentError(Exception):
    """Error dasar untuk agent dan registry."""

    def __init__(self, agent_id: str, message: str) -> None:
        """Inisialisasi error.

        Args:
            agent_id: ID agent yang terkait.
            message: Pesan error untuk log dan response API.
        """
        super().__init__(message)
        self.agent_id = agent_id


class AgentNotFoundError(AgentError):
    """Tidak ada agent dengan ID ini di registry (HTTP 404).

    >>> str(AgentNotFoundError("missing"))
    "Agent 'missing' not found"
    """

    def __init__(self, agent_id: str) -> None:
        """Inisialisasi error.

        Args:
            agent_id: ID agent yang diminta.
        """
        super().__init__(agent_id, f"Agent {agent_id!r} not found")


class AgentUnavailableError(AgentError):
    """Agent terdaftar, tapi belum dimuat atau gagal dimuat (HTTP 503)."""

    def __init__(self, agent_id: str) -> None:
        """Inisialisasi error.

        Args:
            agent_id: ID agent yang diminta.
        """
        super().__init__(agent_id, f"Agent {agent_id!r} is unavailable")


class DuplicateAgentError(AgentError):
    """Agent dengan ID yang sama sudah terdaftar."""

    def __init__(self, agent_id: str) -> None:
        """Inisialisasi error.

        Args:
            agent_id: ID agent yang didaftarkan dua kali.
        """
        super().__init__(agent_id, f"Agent {agent_id!r} is already registered")


class AgentStepLimitError(AgentError):
    """Run melewati `recursion_limit` sebelum agent selesai (HTTP 500, FR-59).

    >>> str(AgentStepLimitError("chatbot")) == STEP_LIMIT_ERROR_DETAIL
    True
    """

    def __init__(self, agent_id: str) -> None:
        """Inisialisasi error.

        Args:
            agent_id: ID agent yang run-nya dihentikan.
        """
        super().__init__(agent_id, STEP_LIMIT_ERROR_DETAIL)
