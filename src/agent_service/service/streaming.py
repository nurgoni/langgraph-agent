"""Streaming run agent sebagai Server-Sent Events (FR-7, PRD §7.3)."""

import logging
from collections.abc import AsyncGenerator, Iterable, Mapping
from typing import Final

from langchain_core.messages import AIMessageChunk, BaseMessage, HumanMessage
from langgraph.types import Interrupt, StreamMode

from agent_service.agents.base import AgentGraph
from agent_service.agents.supervisor import SUBAGENT_TAG
from agent_service.llm.reasoning import message_reasoning
from agent_service.schema.responses import ChatMessage
from agent_service.schema.stream import (
    STREAM_DONE_MARKER,
    ErrorEvent,
    MessageEvent,
    ReasoningEvent,
    StreamEvent,
    TokenEvent,
)
from agent_service.service.converters import (
    INTERRUPT_KEY,
    MESSAGES_KEY,
    UnsupportedMessageError,
    content_to_text,
    interrupt_to_chat_message,
    langchain_to_chat_message,
)
from agent_service.service.run_input import RunInput

logger = logging.getLogger(__name__)

UPDATES_MODE: Final = "updates"
MESSAGES_MODE: Final = "messages"
CUSTOM_MODE: Final = "custom"
STREAM_MODES: Final[list[StreamMode]] = [UPDATES_MODE, MESSAGES_MODE, CUSTOM_MODE]
# Node yang memanggil LLM untuk keperluan internal (misalnya klasifikasi) diberi tag ini supaya
# tokennya tidak tampil ke user.
SKIP_STREAM_TAG: Final = "skip_stream"
STREAM_ERROR_DETAIL: Final = "Internal server error"

SSE_DATA_PREFIX: Final = "data: "
SSE_FRAME_END: Final = "\n\n"
DONE_FRAME: Final = f"{SSE_DATA_PREFIX}{STREAM_DONE_MARKER}{SSE_FRAME_END}"


def sse_frame(event: StreamEvent) -> str:
    """Bungkus event menjadi satu frame SSE `data: <json>`.

    Function, bukan class: transformasi murni tanpa state.

    >>> from agent_service.schema.stream import TokenEvent
    >>> sse_frame(TokenEvent(content="Hal"))
    'data: {"type":"token","content":"Hal"}\\n\\n'
    >>> DONE_FRAME
    'data: [DONE]\\n\\n'
    """
    return f"{SSE_DATA_PREFIX}{event.model_dump_json()}{SSE_FRAME_END}"


class StreamService:
    """Mengubah satu run graph menjadi frame SSE, dibuat per request `/stream`.

    Class karena graph, input run, dan opsi token dipakai bersama oleh beberapa handler per jenis
    event, sehingga tidak perlu dioper ke setiap function.
    """

    def __init__(self, graph: AgentGraph, run: RunInput, stream_tokens: bool) -> None:
        """Inisialisasi streamer.

        Args:
            graph: Graph agent untuk model yang dipilih.
            run: Input dan config run dari `build_run_input`.
            stream_tokens: Kirim frame `token` dari LLM (`StreamInput.stream_tokens`).
        """
        self._graph = graph
        self._run = run
        self._stream_tokens = stream_tokens
        self._run_id = str(run.run_id)
        # Message expert dikirim lebih awal lewat mode `custom`, lalu muncul lagi di update node
        # `delegate`. ID yang sudah terkirim dicatat supaya tidak dikirim dua kali.
        self._sent_message_ids: set[str] = set()

    async def stream(self) -> AsyncGenerator[str]:
        """Jalankan graph dan hasilkan frame SSE, selalu diakhiri `[DONE]`.

        Error di tengah run menjadi frame `error` dengan pesan generik. Saat client memutus
        koneksi, generator ditutup tanpa `[DONE]`, karena tidak ada lagi yang menerima.
        """
        try:
            async for event in self._events():
                yield sse_frame(event)
        # Batas sistem: error apa pun dari agent tidak boleh memutus stream tanpa frame penutup.
        except Exception:
            logger.exception("Stream failed run_id=%s", self._run_id)
            yield sse_frame(ErrorEvent(content=STREAM_ERROR_DETAIL))
        yield DONE_FRAME

    async def _events(self) -> AsyncGenerator[StreamEvent]:
        """Teruskan setiap item `astream` ke handler sesuai stream mode."""
        async for mode, payload in self._graph.astream(
            self._run.graph_input, self._run.config, stream_mode=STREAM_MODES
        ):
            if mode == UPDATES_MODE:
                events = self._handle_updates(payload)
            elif mode == MESSAGES_MODE:
                events = self._handle_message_chunk(payload)
            else:
                events = self._handle_custom(payload)
            for event in events:
                yield event

    def _handle_updates(self, updates: object) -> list[StreamEvent]:
        """Message baru dari setiap node, dan pertanyaan interrupt (FR-12)."""
        if not isinstance(updates, Mapping):
            return []
        events: list[StreamEvent] = []
        for node, update in updates.items():
            if node == INTERRUPT_KEY:
                events.extend(self._interrupt_events(update))
            elif isinstance(update, Mapping):
                events.extend(self._message_events(update.get(MESSAGES_KEY, [])))
        return events

    def _handle_message_chunk(self, payload: object) -> list[StreamEvent]:
        """Reasoning dan token LLM dari `(chunk, metadata)` (FR-29).

        Tidak ada event jika token dimatikan, run bertag `skip_stream` atau `subagent`, atau chunk
        kosong.
        Reasoning dikirim lebih dulu karena model memikirkannya sebelum menjawab.
        """
        if not self._stream_tokens or not isinstance(payload, tuple):
            return []
        chunk, metadata = payload
        if not isinstance(chunk, AIMessageChunk):
            return []
        tags = metadata.get("tags") or []
        # Token expert tidak masuk ke chat utama. Message utuhnya tetap dikirim lewat `updates`.
        if SKIP_STREAM_TAG in tags or SUBAGENT_TAG in tags:
            return []
        events: list[StreamEvent] = []
        reasoning = message_reasoning(chunk)
        if reasoning:
            events.append(ReasoningEvent(content=reasoning))
        text = content_to_text(chunk.content)
        if text:
            events.append(TokenEvent(content=text))
        return events

    def _handle_custom(self, payload: object) -> list[StreamEvent]:
        """Event dari `get_stream_writer()`: message LangChain, atau dict sebagai message custom."""
        if isinstance(payload, BaseMessage):
            return self._message_events([payload])
        if isinstance(payload, dict):
            return [
                self._message_event(ChatMessage(type="custom", content="", custom_data=payload))
            ]
        logger.warning("Dropping custom stream event of type %s", type(payload).__name__)
        return []

    def _interrupt_events(self, interrupts: Iterable[Interrupt]) -> list[StreamEvent]:
        """Pertanyaan interrupt sebagai message AI."""
        events: list[StreamEvent] = []
        for interrupt in interrupts:
            events.append(self._message_event(interrupt_to_chat_message(interrupt)))
        return events

    def _message_events(self, messages: Iterable[BaseMessage]) -> list[StreamEvent]:
        """Message LangChain sebagai frame `message`.

        Message human (echo input) dan message yang sudah pernah dikirim (berdasarkan `id`)
        dilewati.
        """
        events: list[StreamEvent] = []
        for message in messages:
            if isinstance(message, HumanMessage) or message.id in self._sent_message_ids:
                continue
            if message.id is not None:
                self._sent_message_ids.add(message.id)
            try:
                chat_message = langchain_to_chat_message(message)
            except UnsupportedMessageError:
                logger.warning("Dropping unsupported %s from stream", type(message).__name__)
                continue
            events.append(self._message_event(chat_message))
        return events

    def _message_event(self, chat_message: ChatMessage) -> MessageEvent:
        """Bungkus message dengan `run_id` run ini."""
        return MessageEvent(content=chat_message.model_copy(update={"run_id": self._run_id}))
