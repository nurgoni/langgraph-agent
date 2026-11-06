import pytest

from agent_service.client.errors import AgentClientError
from agent_service.client.sse import SseParser
from agent_service.schema.responses import ChatMessage
from agent_service.schema.stream import ErrorEvent, MessageEvent, StreamEvent, TokenEvent


def feed(parser: SseParser, *lines: str) -> list[StreamEvent]:
    events: list[StreamEvent] = []
    for line in lines:
        event = parser.feed_line(line)
        if event is not None:
            events.append(event)
    return events


def test_frames_are_parsed_in_order() -> None:
    parser = SseParser()

    events = feed(
        parser,
        'data: {"type": "token", "content": "Hal"}',
        "",
        'data: {"type": "message", "content": {"type": "ai", "content": "Halo"}}',
        "",
        'data: {"type": "error", "content": "boom"}',
        "",
        "data: [DONE]",
        "",
    )

    assert events == [
        TokenEvent(content="Hal"),
        MessageEvent(content=ChatMessage(type="ai", content="Halo")),
        ErrorEvent(content="boom"),
    ]
    assert parser.done


def test_multiline_data_is_joined() -> None:
    parser = SseParser()

    events = feed(parser, 'data: {"type": "token",', 'data: "content": "x"}', "")

    assert events == [TokenEvent(content="x")]


def test_comments_other_fields_and_extra_blank_lines_are_ignored() -> None:
    parser = SseParser()

    events = feed(parser, ": keep-alive", "", "event: token", "id: 1", "", "")

    assert events == []
    assert not parser.done


def test_data_without_space_after_colon_is_accepted() -> None:
    assert feed(SseParser(), 'data:{"type": "token", "content": "a"}', "") == [
        TokenEvent(content="a")
    ]


def test_flush_returns_frame_without_trailing_blank_line() -> None:
    parser = SseParser()
    parser.feed_line('data: {"type": "token", "content": "a"}')

    assert parser.flush() == TokenEvent(content="a")
    assert parser.flush() is None


def test_invalid_frame_raises_client_error() -> None:
    parser = SseParser()
    parser.feed_line('data: {"type": "unknown"}')

    with pytest.raises(AgentClientError, match="Invalid stream frame"):
        parser.flush()


def test_finish_accepts_done_without_trailing_blank_line() -> None:
    parser = SseParser()
    parser.feed_line("data: [DONE]")

    assert parser.finish() is None
    assert parser.done


def test_finish_without_done_raises() -> None:
    parser = SseParser()
    feed(parser, 'data: {"type": "token", "content": "a"}', "")

    with pytest.raises(AgentClientError, match="before \[DONE\]"):
        parser.finish()
