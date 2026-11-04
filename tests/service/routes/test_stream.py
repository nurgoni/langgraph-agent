from typing import Any

import pytest
from httpx import AsyncClient

from agent_service.llm.fake import DEFAULT_FAKE_RESPONSE
from agent_service.schema.headers import THREAD_ID_HEADER, USER_ID_HEADER
from agent_service.schema.stream import STREAM_EVENT_ADAPTER, MessageEvent, StreamEvent, TokenEvent

OWNER = "user-a"
DONE_LINE = "data: [DONE]"


async def stream_events(
    client: AsyncClient,
    path: str,
    **body: Any,  # Any: body JSON
) -> tuple[list[StreamEvent], dict[str, str]]:
    async with client.stream("POST", path, json=body) as response:
        assert response.status_code == 200, await response.aread()
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = [line async for line in response.aiter_lines() if line]
    assert lines[-1] == DONE_LINE
    events: list[StreamEvent] = []
    for line in lines[:-1]:
        events.append(STREAM_EVENT_ADAPTER.validate_json(line.removeprefix("data: ")))
    return events, dict(response.headers)


async def test_stream_sends_tokens_message_and_done(client: AsyncClient) -> None:
    events, _ = await stream_events(client, "/chatbot/stream", message="Halo")

    tokens = [event.content for event in events if isinstance(event, TokenEvent)]
    messages = [event.content for event in events if isinstance(event, MessageEvent)]
    assert "".join(tokens) == DEFAULT_FAKE_RESPONSE
    assert [(m.type, m.content) for m in messages] == [("ai", DEFAULT_FAKE_RESPONSE)]
    assert messages[0].run_id


async def test_default_agent_route_streams(client: AsyncClient) -> None:
    events, _ = await stream_events(client, "/stream", message="Halo", stream_tokens=False)

    assert len(events) == 1


async def test_stream_returns_id_headers(client: AsyncClient) -> None:
    _, headers = await stream_events(
        client, "/chatbot/stream", message="Halo", thread_id="t1", user_id=OWNER
    )

    assert headers[THREAD_ID_HEADER.lower()] == "t1"
    assert headers[USER_ID_HEADER.lower()] == OWNER


async def test_streamed_turn_is_kept_in_history(client: AsyncClient) -> None:
    await stream_events(client, "/chatbot/stream", message="Halo", thread_id="t1", user_id=OWNER)

    history = await client.post("/chatbot/history", json={"thread_id": "t1", "user_id": OWNER})

    assert [m["type"] for m in history.json()["messages"]] == ["human", "ai"]


async def test_interrupt_question_then_resume_over_stream(client: AsyncClient) -> None:
    ids = {"thread_id": "t1", "user_id": OWNER}

    question, _ = await stream_events(client, "/interrupt/stream", message="Hai", **ids)
    answer, _ = await stream_events(client, "/interrupt/stream", message="Budi", **ids)

    assert [e.content.content for e in question if isinstance(e, MessageEvent)] == [
        "What is your name?"
    ]
    assert [e.content.content for e in answer if isinstance(e, MessageEvent)] == ["Hello Budi"]


@pytest.mark.parametrize(
    ("path", "body", "expected_status"),
    [
        ("/ghost/stream", {"message": "Hai"}, 404),
        ("/chatbot/stream", {"message": "Hai", "model": "gpt-x"}, 422),
        ("/tone/stream", {"message": "Hai", "agent_config": {"max_words": "many"}}, 422),
        ("/chatbot/stream", {"message": ""}, 422),
    ],
)
async def test_invalid_request_fails_before_streaming(
    client: AsyncClient, path: str, body: dict[str, Any], expected_status: int
) -> None:
    response = await client.post(path, json=body)

    assert response.status_code == expected_status
    assert response.headers["content-type"] == "application/json"


async def test_other_users_thread_is_404(client: AsyncClient) -> None:
    await stream_events(client, "/chatbot/stream", message="Halo", thread_id="t1", user_id=OWNER)

    response = await client.post(
        "/chatbot/stream", json={"message": "Hai", "thread_id": "t1", "user_id": "user-b"}
    )

    assert response.status_code == 404
