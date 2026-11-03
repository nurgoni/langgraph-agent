"""Model event SSE untuk endpoint `/stream` (PRD §7.3).

Setiap frame berupa `data: <json>`, dan stream selalu diakhiri `data: [DONE]`.

>>> event = STREAM_EVENT_ADAPTER.validate_json('{"type": "token", "content": "Hal"}')
>>> type(event).__name__, event.content
('TokenEvent', 'Hal')
"""

from typing import Annotated, Final, Literal

from pydantic import BaseModel, Field, TypeAdapter

from agent_service.schema.responses import ChatMessage

STREAM_DONE_MARKER: Final = "[DONE]"


class TokenEvent(BaseModel):
    """Potongan teks dari LLM, dikirim saat `stream_tokens=True`."""

    type: Literal["token"] = "token"
    content: str


class MessageEvent(BaseModel):
    """Message utuh: jawaban AI, tool call, hasil tool, atau event custom."""

    type: Literal["message"] = "message"
    content: ChatMessage


class ErrorEvent(BaseModel):
    """Error saat agent berjalan. Stream tetap diakhiri `[DONE]` setelah event ini."""

    type: Literal["error"] = "error"
    content: str


StreamEvent = Annotated[TokenEvent | MessageEvent | ErrorEvent, Field(discriminator="type")]

# Stateless dan tanpa I/O, jadi aman dibuat sekali saat import dan dipakai ulang oleh client.
STREAM_EVENT_ADAPTER: Final[TypeAdapter[StreamEvent]] = TypeAdapter(StreamEvent)


if __name__ == "__main__":
    events: list[StreamEvent] = [
        TokenEvent(content="Hal"),
        MessageEvent(content=ChatMessage(type="ai", content="Halo!")),
    ]
    for event in events:
        print(f"data: {event.model_dump_json()}")
    print(f"data: {STREAM_DONE_MARKER}")
