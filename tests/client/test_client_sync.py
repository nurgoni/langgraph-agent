import json
from collections.abc import Callable, Iterator

import httpx
import pytest

from agent_service.client import AgentClient, AgentClientError, ServiceUnreachableError
from agent_service.client.stream import StreamNotStartedError
from agent_service.schema.headers import THREAD_ID_HEADER, USER_ID_HEADER
from agent_service.schema.stream import ErrorEvent, MessageEvent, TokenEvent

BASE_URL = "http://agent.test"
ID_HEADERS = {THREAD_ID_HEADER: "t1", USER_ID_HEADER: "u1"}
AI_MESSAGE = {"type": "ai", "content": "Halo!", "run_id": "r1"}
INFO = {
    "agents": [{"key": "chatbot", "description": "Bot", "config_schema": {}}],
    "models": ["fake"],
    "default_agent": "chatbot",
    "default_model": "fake",
}
SSE_BODY = (
    'data: {"type": "token", "content": "Hal"}\n\n'
    'data: {"type": "token", "content": "o!"}\n\n'
    f'data: {{"type": "message", "content": {json.dumps(AI_MESSAGE)}}}\n\n'
    "data: [DONE]\n\n"
)

type Handler = Callable[[httpx.Request], httpx.Response]


class RecordingTransport(httpx.MockTransport):
    """MockTransport yang menyimpan setiap request untuk diperiksa test."""

    def __init__(self, handler: Handler) -> None:
        self.requests: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return handler(request)

        super().__init__(record)


def make_client(
    handler: Handler, agent_id: str | None = "chatbot", auth_secret: str | None = None
) -> tuple[AgentClient, RecordingTransport]:
    transport = RecordingTransport(handler)
    client = AgentClient(
        base_url=BASE_URL, agent_id=agent_id, auth_secret=auth_secret, transport=transport
    )
    return client, transport


def test_constructor_sends_no_request() -> None:
    client, transport = make_client(lambda request: httpx.Response(500))

    client.close()

    assert transport.requests == []


def test_info_is_fetched_lazily_and_cached() -> None:
    client, transport = make_client(lambda request: httpx.Response(200, json=INFO))

    with client:
        first = client.get_info()
        second = client.get_info()
        client.get_info(refresh=True)

    assert first is second
    assert first.default_agent == "chatbot"
    assert len(transport.requests) == 2


def test_invoke_posts_payload_and_returns_reply_with_ids() -> None:
    client, transport = make_client(
        lambda request: httpx.Response(200, json=AI_MESSAGE, headers=ID_HEADERS)
    )

    with client:
        reply = client.invoke("Hai", model="fake", user_id="u1", agent_config={"tone": "x"})

    [request] = transport.requests
    assert (request.method, request.url.path) == ("POST", "/chatbot/invoke")
    assert json.loads(request.content) == {
        "message": "Hai",
        "model": "fake",
        "user_id": "u1",
        "agent_config": {"tone": "x"},
    }
    assert (reply.message.content, reply.thread_id, reply.user_id) == ("Halo!", "t1", "u1")


def test_no_agent_id_uses_default_agent_routes() -> None:
    client, transport = make_client(
        lambda request: httpx.Response(200, json=AI_MESSAGE, headers=ID_HEADERS), agent_id=None
    )

    with client:
        client.invoke("Hai")

    assert transport.requests[0].url.path == "/invoke"


def test_auth_secret_is_sent_as_bearer_token() -> None:
    client, transport = make_client(
        lambda request: httpx.Response(200, json=INFO), auth_secret="s3cret"
    )

    with client:
        client.get_info()

    assert transport.requests[0].headers["authorization"] == "Bearer s3cret"


def test_http_error_carries_status_and_detail() -> None:
    client, _ = make_client(
        lambda request: httpx.Response(404, json={"detail": "Agent 'ghost' not found"})
    )

    with client, pytest.raises(AgentClientError) as error_info:
        client.invoke("Hai")

    assert error_info.value.status_code == 404
    assert error_info.value.detail == "Agent 'ghost' not found"
    assert "POST /chatbot/invoke failed with 404" in str(error_info.value)


def test_validation_error_keeps_field_list() -> None:
    detail = [{"type": "missing", "loc": ["query", "user_id"], "msg": "Field required"}]
    client, _ = make_client(lambda request: httpx.Response(422, json={"detail": detail}))

    with client, pytest.raises(AgentClientError) as error_info:
        client.get_threads("u1")

    assert error_info.value.detail == detail


def test_non_json_error_body_becomes_text_detail() -> None:
    client, _ = make_client(lambda request: httpx.Response(502, text="Bad Gateway"))

    with client, pytest.raises(AgentClientError) as error_info:
        client.get_info()

    assert (error_info.value.status_code, error_info.value.detail) == (502, "Bad Gateway")


def test_connection_error_is_service_unreachable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client, _ = make_client(refuse)

    with client, pytest.raises(AgentClientError) as error_info:
        client.get_info()

    assert error_info.value.status_code is None
    assert isinstance(error_info.value, ServiceUnreachableError)


def test_unexpected_body_raises_client_error() -> None:
    client, _ = make_client(lambda request: httpx.Response(200, json={"unexpected": True}))

    with client, pytest.raises(AgentClientError, match="Unexpected response"):
        client.get_info()


def test_missing_id_headers_raise_client_error() -> None:
    client, _ = make_client(lambda request: httpx.Response(200, json=AI_MESSAGE))

    with client, pytest.raises(AgentClientError, match="X-Thread-Id"):
        client.invoke("Hai")


def test_history_threads_rename_and_delete_requests() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        responses = {
            "POST": httpx.Response(200, json={"messages": [AI_MESSAGE]}),
            "GET": httpx.Response(200, json={"threads": []}),
            "PATCH": httpx.Response(
                200, json={"thread_id": "t/1", "agent_id": "chatbot", "title": "Baru"}
            ),
            "DELETE": httpx.Response(204),
        }
        return responses[request.method]

    client, transport = make_client(respond)

    with client:
        history = client.get_history("t1", "u1")
        threads = client.get_threads("u1", limit=5)
        summary = client.rename_thread("t/1", "u1", "Baru")
        client.delete_thread("t/1", "u1")

    history_req, threads_req, rename_req, delete_req = transport.requests
    assert json.loads(history_req.content) == {"thread_id": "t1", "user_id": "u1"}
    assert history.messages[0].content == "Halo!"
    assert dict(threads_req.url.params) == {"user_id": "u1", "limit": "5"}
    assert threads.threads == []
    assert rename_req.url.raw_path == b"/chatbot/threads/t%2F1"
    assert json.loads(rename_req.content) == {"user_id": "u1", "title": "Baru"}
    assert summary.title == "Baru"
    assert delete_req.url.raw_path == b"/chatbot/threads/t%2F1?user_id=u1"


def test_stream_exposes_ids_and_yields_events() -> None:
    client, transport = make_client(
        lambda request: httpx.Response(200, text=SSE_BODY, headers=ID_HEADERS)
    )

    with client, client.stream("Hai", stream_tokens=False) as run:
        events = list(run)
        ids = (run.thread_id, run.user_id)

    assert json.loads(transport.requests[0].content)["stream_tokens"] is False
    assert ids == ("t1", "u1")
    assert [type(event) for event in events] == [TokenEvent, TokenEvent, MessageEvent]


def test_stream_error_frame_is_yielded_not_raised() -> None:
    body = 'data: {"type": "error", "content": "Internal server error"}\n\ndata: [DONE]\n\n'
    client, _ = make_client(lambda request: httpx.Response(200, text=body, headers=ID_HEADERS))

    with client, client.stream("Hai") as run:
        events = list(run)

    assert events == [ErrorEvent(content="Internal server error")]


def test_stream_http_error_raises_on_enter() -> None:
    client, _ = make_client(lambda request: httpx.Response(422, json={"detail": [{"msg": "x"}]}))

    with client, pytest.raises(AgentClientError) as error_info, client.stream("Hai"):
        pass

    assert error_info.value.status_code == 422


def test_stream_without_done_raises() -> None:
    body = 'data: {"type": "token", "content": "Hal"}\n\n'
    client, _ = make_client(lambda request: httpx.Response(200, text=body, headers=ID_HEADERS))

    with client, client.stream("Hai") as run, pytest.raises(AgentClientError, match="DONE"):
        list(run)


def test_stream_connection_error_raises_on_enter() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client, _ = make_client(refuse)

    with client, pytest.raises(AgentClientError, match="Stream request failed"), client.stream("x"):
        pass


def test_stream_ids_require_with_block() -> None:
    client, transport = make_client(lambda request: httpx.Response(200))

    with client:
        run = client.stream("Hai")
        with pytest.raises(StreamNotStartedError):
            _ = run.thread_id

    assert transport.requests == []


class BrokenStream(httpx.SyncByteStream):
    """Body yang mengirim satu frame lalu koneksinya putus."""

    def __iter__(self) -> Iterator[bytes]:
        yield b'data: {"type": "token", "content": "Hal"}\n\n'
        raise httpx.ReadError("connection reset")


def test_stream_interrupted_mid_body_raises() -> None:
    client, _ = make_client(
        lambda request: httpx.Response(200, stream=BrokenStream(), headers=ID_HEADERS)
    )

    with client, client.stream("Hai") as run:
        events = run.__iter__()
        assert next(events) == TokenEvent(content="Hal")
        with pytest.raises(AgentClientError, match="Stream interrupted"):
            next(events)


def test_json_error_without_detail_keeps_whole_body() -> None:
    client, _ = make_client(lambda request: httpx.Response(500, json={"error": "boom"}))

    with client, pytest.raises(AgentClientError) as error_info:
        client.get_info()

    assert error_info.value.detail == {"error": "boom"}


def test_base_url_is_exposed_without_trailing_slash() -> None:
    client, _ = make_client(lambda request: httpx.Response(200))

    with client:
        assert client.base_url == BASE_URL


def test_read_timeout_is_not_reported_as_unreachable() -> None:
    def time_out(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    client, _ = make_client(time_out)

    with client, pytest.raises(AgentClientError) as error_info:
        client.get_info()

    assert not isinstance(error_info.value, ServiceUnreachableError)
