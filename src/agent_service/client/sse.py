"""Parser Server-Sent Events untuk respons `/stream` (PRD §7.3)."""

from typing import Final

from pydantic import ValidationError

from agent_service.client.errors import AgentClientError
from agent_service.schema.stream import STREAM_DONE_MARKER, STREAM_EVENT_ADAPTER, StreamEvent

DATA_FIELD: Final = "data"
FIELD_SEPARATOR: Final = ":"
COMMENT_PREFIX: Final = ":"
VALUE_LEADING_SPACE: Final = " "
DATA_LINE_JOINER: Final = "\n"


class SseParser:
    """Menyusun baris SSE menjadi `StreamEvent`, satu frame per baris kosong.

    Class karena menyimpan state antar baris: baris `data:` yang belum lengkap dan status
    `[DONE]`. Field selain `data` (`event`, `id`, `retry`) dan komentar diabaikan.

    >>> parser = SseParser()
    >>> parser.feed_line('data: {"type": "token", "content": "Hal"}')
    >>> parser.feed_line("")
    TokenEvent(type='token', content='Hal')
    >>> parser.feed_line("data: [DONE]"), parser.feed_line(""), parser.done
    (None, None, True)
    """

    def __init__(self) -> None:
        """Inisialisasi parser kosong."""
        self._data_lines: list[str] = []
        self.done = False

    def feed_line(self, line: str) -> StreamEvent | None:
        """Proses satu baris tanpa karakter newline.

        Args:
            line: Satu baris dari body respons.

        Returns:
            Event jika baris ini menutup sebuah frame, selain itu `None`.

        Raises:
            AgentClientError: Jika isi frame bukan event yang valid.
        """
        if not line:
            return self.flush()
        if line.startswith(COMMENT_PREFIX):
            return None
        field, _, value = line.partition(FIELD_SEPARATOR)
        if field == DATA_FIELD:
            self._data_lines.append(value.removeprefix(VALUE_LEADING_SPACE))
        return None

    def flush(self) -> StreamEvent | None:
        """Tutup frame yang sedang disusun, misalnya saat body berakhir tanpa baris kosong.

        Returns:
            Event dari frame tersebut, atau `None` jika frame kosong atau berupa `[DONE]`.

        Raises:
            AgentClientError: Jika isi frame bukan event yang valid.
        """
        if not self._data_lines:
            return None
        data = DATA_LINE_JOINER.join(self._data_lines)
        self._data_lines.clear()
        if data == STREAM_DONE_MARKER:
            self.done = True
            return None
        try:
            return STREAM_EVENT_ADAPTER.validate_json(data)
        except ValidationError as error:
            raise AgentClientError(f"Invalid stream frame: {data[:100]!r}") from error

    def finish(self) -> None:
        """Tutup parser saat body respons berakhir, termasuk `[DONE]` tanpa baris kosong penutup.

        Raises:
            AgentClientError: Jika stream berakhir sebelum `[DONE]` (koneksi terputus atau respons
                terpotong), atau frame terakhir tidak valid.
        """
        self.flush()
        if not self.done:
            raise AgentClientError("Stream ended before [DONE]")
