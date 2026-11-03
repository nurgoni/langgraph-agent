import json

import pytest
from pydantic import ValidationError

from agent_service.schema.responses import ChatMessage
from agent_service.schema.stream import (
    STREAM_EVENT_ADAPTER,
    ErrorEvent,
    MessageEvent,
    TokenEvent,
)


def test_token_event_serializes_to_prd_frame_shape() -> None:
    payload = json.loads(TokenEvent(content="Hal").model_dump_json())

    assert payload == {"type": "token", "content": "Hal"}


def test_message_event_nests_chat_message() -> None:
    event = MessageEvent(content=ChatMessage(type="ai", content="Halo!"))

    payload = json.loads(event.model_dump_json())

    assert payload["type"] == "message"
    assert payload["content"]["type"] == "ai"
    assert payload["content"]["content"] == "Halo!"


@pytest.mark.parametrize(
    ("raw", "expected_class"),
    [
        ('{"type": "token", "content": "a"}', TokenEvent),
        ('{"type": "message", "content": {"type": "ai", "content": "b"}}', MessageEvent),
        ('{"type": "error", "content": "boom"}', ErrorEvent),
    ],
)
def test_adapter_selects_event_class_by_type(raw: str, expected_class: type) -> None:
    assert isinstance(STREAM_EVENT_ADAPTER.validate_json(raw), expected_class)


def test_adapter_rejects_unknown_event_type() -> None:
    with pytest.raises(ValidationError):
        STREAM_EVENT_ADAPTER.validate_json('{"type": "unknown", "content": "x"}')
