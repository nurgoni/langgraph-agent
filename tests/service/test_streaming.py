import json

from agent_service.schema.responses import ChatMessage
from agent_service.schema.stream import (
    STREAM_EVENT_ADAPTER,
    ErrorEvent,
    MessageEvent,
    TokenEvent,
)
from agent_service.service.streaming import DONE_FRAME, sse_frame


def parse_frame(frame: str) -> object:
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    return json.loads(frame.removeprefix("data: ").removesuffix("\n\n"))


def test_token_frame_matches_prd_shape() -> None:
    assert parse_frame(sse_frame(TokenEvent(content="Hal"))) == {"type": "token", "content": "Hal"}


def test_message_frame_round_trips_through_adapter() -> None:
    event = MessageEvent(content=ChatMessage(type="ai", content="Halo!", run_id="r1"))

    frame = sse_frame(event)

    payload = frame.removeprefix("data: ").removesuffix("\n\n")
    assert STREAM_EVENT_ADAPTER.validate_json(payload) == event


def test_error_frame_matches_prd_shape() -> None:
    assert parse_frame(sse_frame(ErrorEvent(content="boom"))) == {
        "type": "error",
        "content": "boom",
    }


def test_done_frame_is_literal_marker() -> None:
    assert DONE_FRAME == "data: [DONE]\n\n"
