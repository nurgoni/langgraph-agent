"""Trace run agent (FR-41): callback LangChain yang mencatat panggilan model dan tool.

Satu `RunTraceCollector` dibuat per request `/invoke` atau `/stream` dan dipasang di
`config["callbacks"]`. Span disimpan di memori selama run, lalu ditulis sekaligus oleh `save()`
di akhir run, jadi tidak ada query database di tengah panggilan model. Kegagalan menulis trace
dicatat di log tanpa menggagalkan jawaban ke user.

Isi prompt, jawaban, dan hasil tool tidak dicatat (keputusan F31): trace hanya berisi nama, waktu,
status, dan jumlah token.
"""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import ChatGeneration, LLMResult
from langgraph.errors import GraphBubbleUp
from sqlalchemy.exc import SQLAlchemyError

from agent_service.memory.traces import (
    RunTraceRepository,
    SpanKind,
    SpanStatus,
    TraceSpanRecord,
)
from agent_service.service.run_input import RunInput

logger = logging.getLogger(__name__)

MODEL_NAME_METADATA_KEY: Final = "ls_model_name"
DEFAULT_MODEL_SPAN_NAME: Final = "model"
DEFAULT_TOOL_SPAN_NAME: Final = "tool"
ERROR_MAX_CHARS: Final = 500
MILLISECONDS_PER_SECOND: Final = 1000

type Clock = Callable[[], datetime]


def utc_now() -> datetime:
    """Waktu sekarang dalam UTC, dihitung setiap kali dipanggil."""
    return datetime.now(UTC)


def duration_ms(started_at: datetime, ended_at: datetime) -> int:
    """Selisih waktu dalam milidetik, dibulatkan ke bawah.

    >>> from datetime import timedelta
    >>> start = datetime(2026, 11, 17, tzinfo=UTC)
    >>> duration_ms(start, start + timedelta(seconds=1.5))
    1500
    """
    return int((ended_at - started_at).total_seconds() * MILLISECONDS_PER_SECOND)


def describe_error(error: BaseException) -> str:
    """Nama exception dan pesannya, dipotong ke `ERROR_MAX_CHARS`.

    >>> describe_error(ValueError("bad input"))
    'ValueError: bad input'
    """
    return f"{type(error).__name__}: {error}"[:ERROR_MAX_CHARS]


def error_status(error: BaseException) -> SpanStatus:
    """`interrupted` untuk interrupt LangGraph (bukan kegagalan), selain itu `error`."""
    return "interrupted" if isinstance(error, GraphBubbleUp) else "error"


@dataclass
class _OpenSpan:
    """Span yang sudah mulai tetapi belum selesai."""

    kind: SpanKind
    name: str
    started_at: datetime


class RunTraceCollector(AsyncCallbackHandler):
    """Mengumpulkan span model dan tool satu run, lalu menyimpannya beserta span `run`."""

    def __init__(
        self,
        repository: RunTraceRepository,
        run: RunInput,
        agent_id: str,
        project_id: str | None,
        clock: Clock = utc_now,
    ) -> None:
        """Mulai trace satu run. Waktu mulai span `run` diambil di sini.

        Args:
            repository: Tempat trace ditulis di akhir run.
            run: Input run, sumber `run_id`, `thread_id`, dan pemilik.
            agent_id: Agent yang menjalankan run.
            project_id: Project run, atau `None` untuk route agent.
            clock: Sumber waktu, bisa diganti di test.
        """
        super().__init__()
        self._repository = repository
        self._run = run
        self._agent_id = agent_id
        self._project_id = project_id
        self._clock = clock
        self._started_at = clock()
        self._open: dict[UUID, _OpenSpan] = {}
        self._spans: list[TraceSpanRecord] = []

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],  # Any: API induk
        messages: list[list[Any]],  # Any: API induk
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,  # Any: API induk
        **kwargs: Any,  # Any: API induk
    ) -> None:
        """Mulai span model. Nama dari metadata LangChain (`ls_model_name`) atau nama class."""
        name = (
            (metadata or {}).get(MODEL_NAME_METADATA_KEY)
            or kwargs.get("name")
            or (serialized or {}).get("name")
        )
        self._open[run_id] = _OpenSpan("model", str(name or DEFAULT_MODEL_SPAN_NAME), self._clock())

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,  # Any: API induk
    ) -> None:
        """Tutup span model beserta token dari `usage_metadata`, jika provider mengirimnya."""
        input_tokens, output_tokens = token_usage(response)
        self._close(run_id, "ok", input_tokens=input_tokens, output_tokens=output_tokens)

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,  # Any: API induk
    ) -> None:
        """Tutup span model yang gagal."""
        self._close(run_id, error_status(error), error=describe_error(error))

    async def on_tool_start(
        self,
        serialized: dict[str, Any],  # Any: API induk
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,  # Any: API induk
    ) -> None:
        """Mulai span tool. Argumen tool tidak dicatat."""
        name = (serialized or {}).get("name") or kwargs.get("name") or DEFAULT_TOOL_SPAN_NAME
        self._open[run_id] = _OpenSpan("tool", str(name), self._clock())

    async def on_tool_end(
        self,
        output: Any,  # Any: API induk
        *,
        run_id: UUID,
        **kwargs: Any,  # Any: API induk
    ) -> None:
        """Tutup span tool yang berhasil."""
        self._close(run_id, "ok")

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,  # Any: API induk
    ) -> None:
        """Tutup span tool yang gagal, atau yang berhenti karena interrupt (`save_memory`)."""
        self._close(run_id, error_status(error), error=describe_error(error))

    def finish(self, status: SpanStatus, error: str | None = None) -> list[TraceSpanRecord]:
        """Tutup trace: span `run` dengan status akhir, diikuti span model/tool urut waktu mulai.

        Span yang belum ditutup (run terputus di tengah panggilan) ditutup dengan status run.
        """
        ended_at = self._clock()
        for open_id in list(self._open):
            self._close(open_id, status)
        run_span = self._record(
            str(self._run.run_id), "run", self._agent_id, status, self._started_at, ended_at
        )
        model_spans = [span for span in self._spans if span.kind == "model"]
        run_span = replace(
            run_span,
            error=error,
            input_tokens=sum_known(span.input_tokens for span in model_spans),
            output_tokens=sum_known(span.output_tokens for span in model_spans),
        )
        return [run_span, *sorted(self._spans, key=lambda span: span.started_at)]

    async def save(self, status: SpanStatus, error: BaseException | None = None) -> None:
        """Tulis trace run ke database. Kegagalan database hanya dicatat di log.

        Args:
            status: Status akhir run.
            error: Exception yang menggagalkan run, jika ada.
        """
        spans = self.finish(status, None if error is None else describe_error(error))
        try:
            await self._repository.add_spans(spans)
        # Trace bersifat pelengkap: database yang gagal tidak boleh mengubah jawaban run.
        except SQLAlchemyError:
            logger.exception("Failed to save trace run_id=%s", self._run.run_id)

    def _close(
        self,
        span_id: UUID,
        status: SpanStatus,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        error: str | None = None,
    ) -> None:
        """Pindahkan span terbuka ke daftar span selesai. ID yang tidak dikenal diabaikan."""
        opened = self._open.pop(span_id, None)
        if opened is None:
            return
        record = self._record(
            str(span_id), opened.kind, opened.name, status, opened.started_at, self._clock()
        )
        self._spans.append(
            replace(record, input_tokens=input_tokens, output_tokens=output_tokens, error=error)
        )

    def _record(
        self,
        span_id: str,
        kind: SpanKind,
        name: str,
        status: SpanStatus,
        started_at: datetime,
        ended_at: datetime,
    ) -> TraceSpanRecord:
        """Span dengan identitas run ini."""
        return TraceSpanRecord(
            span_id=span_id,
            run_id=str(self._run.run_id),
            owner_id=self._run.user_id,
            thread_id=self._run.thread_id,
            agent_id=self._agent_id,
            project_id=self._project_id,
            kind=kind,
            name=name,
            status=status,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=duration_ms(started_at, ended_at),
        )


def sum_known(values: Iterable[int | None]) -> int | None:
    """Jumlah nilai yang diketahui, atau `None` jika tidak ada sama sekali.

    >>> sum_known([3, None, 4]), sum_known([None])
    (7, None)
    """
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def token_usage(response: LLMResult) -> tuple[int | None, int | None]:
    """Token input dan output dari generasi pertama, atau `(None, None)` jika tidak ada.

    >>> from langchain_core.messages import AIMessage
    >>> message = AIMessage("hi", usage_metadata={
    ...     "input_tokens": 12, "output_tokens": 3, "total_tokens": 15})
    >>> token_usage(LLMResult(generations=[[ChatGeneration(message=message)]]))
    (12, 3)
    """
    if not response.generations or not response.generations[0]:
        return None, None
    generation = response.generations[0][0]
    if not isinstance(generation, ChatGeneration):
        return None, None
    usage = getattr(generation.message, "usage_metadata", None)
    if not usage:
        return None, None
    return usage.get("input_tokens"), usage.get("output_tokens")
