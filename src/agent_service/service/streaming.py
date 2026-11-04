"""Streaming run agent sebagai Server-Sent Events (FR-7, PRD §7.3)."""

from typing import Final

from agent_service.schema.stream import STREAM_DONE_MARKER, StreamEvent

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
