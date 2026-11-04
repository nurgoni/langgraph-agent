import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest

from agent_service.client import AgentClient, AgentClientError
from agent_service.client.stream import StreamNotStartedError
from agent_service.schema.headers import THREAD_ID_HEADER, USER_ID_HEADER
from agent_service.schema.stream import ErrorEvent, MessageEvent, TokenEvent

BASE_URL = "http://agent.test"
ID_HEADERS = {THREAD_ID_HEADER: "t1", USER_ID_HEADER: "u1"}
AI_MESSAGE = {"type": "ai", "content": "Halo!"}
INFO = {
    "agents": [{"key": "chatbot", "description": "Bot", "config_schema": {}}],
    "models": ["fake"],
    "default_agent": "chatbot",
    "default_model": "fake",
}
SSE_BODY = (
    'data: {"type": "token", "content": "Hal"}\n\n'
    f'data: {{"type": "message", "content": {json.dumps(AI_MESSAGE)}}}\n\n'
    'data: {"type": "error", "content": "Internal server error"}\n\n'
    "data: [DONE]\n\n"
)

type Handler = Callable[[httpx.Request], httpx.Response]


def respond_with(
    status_code: int, **response_kwargs: Any
) -> Handler:  # Any: argumen httpx.Response
    """Handler MockTransport yang selalu menjawab dengan respons yang sama."""

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, **response_kwargs)

    return respond


def make_client(handler: Handler, requests: list[httpx.Request]) -> AgentClient:
    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    return AgentClient(
        base_url=BASE_URL, agent_id="chatbot", async_transport=httpx.MockTransport(record)
    )


async def test_async_info_is_cached() -> None:
    requests: list[httpx.Request] = []

    async with make_client(lambda request: httpx.Response(200, json=INFO), requests) as client:
        first = await client.aget_info()
        second = await client.aget_info()
        await client.aget_info(refresh=True)

    assert first is second
    assert len(requests) == 2


async def test_ainvoke_returns_reply_with_ids() -> None:
    requests: list[httpx.Request] = []
    handler = respond_with(200, json=AI_MESSAGE, headers=ID_HEADERS)

    async with make_client(handler, requests) as client:
        reply = await client.ainvoke("Hai", thread_id="t1")

    assert json.loads(requests[0].content) == {
        "message": "Hai",
        "thread_id": "t1",
        "agent_config": {},
    }
    assert (reply.message.content, reply.thread_id, reply.user_id) == ("Halo!", "t1", "u1")


async def test_async_thread_operations() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        responses = {
            "POST": httpx.Response(200, json={"messages": []}),
            "GET": httpx.Response(200, json={"threads": []}),
            "PATCH": httpx.Response(
                200, json={"thread_id": "t1", "agent_id": "chatbot", "title": "Baru"}
            ),
            "DELETE": httpx.Response(204),
        }
        return responses[request.method]

    requests: list[httpx.Request] = []
    async with make_client(respond, requests) as client:
        history = await client.aget_history("t1", "u1")
        threads = await client.aget_threads("u1")
        summary = await client.arename_thread("t1", "u1", "Baru")
        await client.adelete_thread("t1", "u1")

    assert [r.method for r in requests] == ["POST", "GET", "PATCH", "DELETE"]
    assert (history.messages, threads.threads, summary.title) == ([], [], "Baru")


async def test_async_http_error_is_wrapped() -> None:
    requests: list[httpx.Request] = []
    handler = respond_with(404, json={"detail": "Thread 't1' not found"})

    async with make_client(handler, requests) as client:
        with pytest.raises(AgentClientError) as error_info:
            await client.aget_history("t1", "u1")

    assert (error_info.value.status_code, error_info.value.detail) == (404, "Thread 't1' not found")


async def test_async_connection_error_is_wrapped() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with make_client(refuse, []) as client:
        with pytest.raises(AgentClientError) as error_info:
            await client.aget_info()

    assert error_info.value.status_code is None


async def test_astream_yields_events_including_error_frame() -> None:
    requests: list[httpx.Request] = []
    handler = respond_with(200, text=SSE_BODY, headers=ID_HEADERS)

    async with make_client(handler, requests) as client, client.astream("Hai") as run:
        events = [event async for event in run]
        ids = (run.thread_id, run.user_id)

    assert ids == ("t1", "u1")
    assert [type(event) for event in events] == [TokenEvent, MessageEvent, ErrorEvent]


async def test_astream_http_error_raises_on_enter() -> None:
    handler = respond_with(404, json={"detail": "Agent 'x' not found"})

    async with make_client(handler, []) as client:
        with pytest.raises(AgentClientError) as error_info:
            async with client.astream("Hai"):
                pass

    assert error_info.value.status_code == 404


async def test_astream_connection_error_raises_on_enter() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with make_client(refuse, []) as client:
        with pytest.raises(AgentClientError, match="Stream request failed"):
            async with client.astream("Hai"):
                pass


async def test_astream_without_done_raises() -> None:
    body = 'data: {"type": "token", "content": "Hal"}\n\n'
    handler = respond_with(200, text=body, headers=ID_HEADERS)

    async with make_client(handler, []) as client, client.astream("Hai") as run:
        with pytest.raises(AgentClientError, match="DONE"):
            _ = [event async for event in run]


class BrokenAsyncStream(httpx.AsyncByteStream):
    """Body async yang mengirim satu frame lalu koneksinya putus."""

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b'data: {"type": "token", "content": "Hal"}\n\n'
        raise httpx.ReadError("connection reset")


async def test_astream_interrupted_mid_body_raises() -> None:
    handler = respond_with(200, stream=BrokenAsyncStream(), headers=ID_HEADERS)

    async with make_client(handler, []) as client, client.astream("Hai") as run:
        events = run.__aiter__()
        assert await anext(events) == TokenEvent(content="Hal")
        with pytest.raises(AgentClientError, match="Stream interrupted"):
            await anext(events)


async def test_astream_ids_require_async_with() -> None:
    async with make_client(lambda request: httpx.Response(200), []) as client:
        run = client.astream("Hai")
        with pytest.raises(StreamNotStartedError):
            _ = run.user_id
