"""Error yang dilempar `AgentClient` (FR-18)."""

from pydantic import JsonValue


class AgentClientError(Exception):
    """Request ke agent service gagal: status HTTP non-2xx, koneksi gagal, atau respons rusak.

    >>> error = AgentClientError("Agent 'x' not found", status_code=404)
    >>> error.status_code, str(error)
    (404, "Agent 'x' not found")
    """

    def __init__(
        self, message: str, status_code: int | None = None, detail: JsonValue = None
    ) -> None:
        """Inisialisasi error.

        Args:
            message: Ringkasan yang bisa dibaca manusia.
            status_code: Status HTTP, atau `None` untuk error koneksi dan respons rusak.
            detail: Isi field `detail` dari respons service: string untuk error domain, list per
                field untuk error validasi 422.
        """
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail
