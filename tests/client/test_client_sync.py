import json
from collections.abc import Callable, Iterator

import httpx
import pytest

from agent_service.client import AgentClient, AgentClientError, ServiceUnreachableError
from agent_service.client.stream import StreamNotStartedError
from agent_service.schema.headers import THREAD_ID_HEADER
from agent_service.schema.projects import ProjectCreate, ProjectUpdate
from agent_service.schema.stream import ErrorEvent, MessageEvent, TokenEvent

BASE_URL = "http://agent.test"
ID_HEADERS = {THREAD_ID_HEADER: "t1"}
TOKEN = {
    "access_token": "jwt-token",
    "token_type": "bearer",
    "expires_in": 43200,
    "user_id": "u1",
    "username": "demo",
    "role": "user",
}
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
    handler: Handler, agent_id: str | None = "chatbot", access_token: str | None = None
) -> tuple[AgentClient, RecordingTransport]:
    transport = RecordingTransport(handler)
    client = AgentClient(
        base_url=BASE_URL, agent_id=agent_id, access_token=access_token, transport=transport
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
        reply = client.invoke("Hai", model="fake", agent_config={"tone": "x"})

    [request] = transport.requests
    assert (request.method, request.url.path) == ("POST", "/chatbot/invoke")
    assert json.loads(request.content) == {
        "message": "Hai",
        "model": "fake",
        "agent_config": {"tone": "x"},
    }
    assert (reply.message.content, reply.thread_id) == ("Halo!", "t1")


def test_no_agent_id_uses_default_agent_routes() -> None:
    client, transport = make_client(
        lambda request: httpx.Response(200, json=AI_MESSAGE, headers=ID_HEADERS), agent_id=None
    )

    with client:
        client.invoke("Hai")

    assert transport.requests[0].url.path == "/invoke"


def test_access_token_is_sent_as_bearer_token() -> None:
    client, transport = make_client(
        lambda request: httpx.Response(200, json=INFO), access_token="jwt-token"
    )

    with client:
        client.get_info()

    assert client.has_access_token
    assert transport.requests[0].headers["authorization"] == "Bearer jwt-token"


def test_login_posts_credentials_and_uses_returned_token() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return httpx.Response(200, json=TOKEN)
        return httpx.Response(200, json=INFO)

    client, transport = make_client(respond)

    with client:
        token = client.login(" Demo ", "rahasia")
        client.get_info()

    login_request, info_request = transport.requests
    assert json.loads(login_request.content) == {"username": "demo", "password": "rahasia"}
    assert "authorization" not in login_request.headers
    assert info_request.headers["authorization"] == "Bearer jwt-token"
    assert (token.username, token.user_id) == ("demo", "u1")


def test_failed_login_keeps_client_without_token() -> None:
    client, _ = make_client(
        lambda request: httpx.Response(401, json={"detail": "Invalid username or password"})
    )

    with client, pytest.raises(AgentClientError) as error_info:
        client.login("demo", "salah")

    assert error_info.value.status_code == 401
    assert not client.has_access_token


def test_clearing_token_logs_out_and_drops_cached_info() -> None:
    client, transport = make_client(
        lambda request: httpx.Response(200, json=INFO), access_token="jwt-token"
    )

    with client:
        client.get_info()
        client.set_access_token(None)
        client.get_info()

    assert not client.has_access_token
    assert "authorization" not in transport.requests[1].headers


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
    detail = [{"type": "less_than_equal", "loc": ["query", "limit"], "msg": "Too big"}]
    client, _ = make_client(lambda request: httpx.Response(422, json={"detail": detail}))

    with client, pytest.raises(AgentClientError) as error_info:
        client.get_threads()

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
        history = client.get_history("t1")
        threads = client.get_threads(limit=5)
        summary = client.rename_thread("t/1", "Baru")
        client.delete_thread("t/1")

    history_req, threads_req, rename_req, delete_req = transport.requests
    assert json.loads(history_req.content) == {"thread_id": "t1"}
    assert history.messages[0].content == "Halo!"
    assert dict(threads_req.url.params) == {"limit": "5"}
    assert threads.threads == []
    assert rename_req.url.raw_path == b"/chatbot/threads/t%2F1"
    assert json.loads(rename_req.content) == {"title": "Baru"}
    assert summary.title == "Baru"
    assert delete_req.url.raw_path == b"/chatbot/threads/t%2F1"


def test_stream_exposes_ids_and_yields_events() -> None:
    client, transport = make_client(
        lambda request: httpx.Response(200, text=SSE_BODY, headers=ID_HEADERS)
    )

    with client, client.stream("Hai", stream_tokens=False) as run:
        events = list(run)
        thread_id = run.thread_id

    assert json.loads(transport.requests[0].content)["stream_tokens"] is False
    assert thread_id == "t1"
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


PROJECT = {
    "id": "p/1",
    "name": "Catatan",
    "description": "",
    "scope": "user",
    "read_only": False,
    "base_agent_id": "chatbot",
    "model": None,
    "instructions": "",
    "skill_ids": [],
    "settings": {"max_tokens": None},
    "created_at": "2026-11-15T00:00:00Z",
    "updated_at": "2026-11-15T00:00:00Z",
}


def test_project_id_routes_chat_and_threads_through_project() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/threads"):
            return httpx.Response(200, json={"threads": []})
        return httpx.Response(200, json=AI_MESSAGE, headers=ID_HEADERS)

    client, transport = make_client(respond)
    client.project_id = "p/1"

    with client:
        client.invoke("Hai")
        client.get_threads()
        client.delete_thread("t1")

    assert [request.url.raw_path for request in transport.requests] == [
        b"/projects/p%2F1/invoke",
        b"/projects/p%2F1/threads?limit=20",
        b"/projects/p%2F1/threads/t1",
    ]


def test_project_crud_requests() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.method == "GET" and request.url.path == "/projects":
            return httpx.Response(200, json={"projects": [PROJECT]})
        return httpx.Response(200, json=PROJECT)

    client, transport = make_client(respond)

    with client:
        listing = client.list_projects()
        client.get_project("p/1")
        client.create_project(ProjectCreate(name="Catatan", base_agent_id="chatbot"))
        client.update_project("p/1", ProjectUpdate(model=None))
        client.delete_project("p/1")

    methods = [(r.method, r.url.raw_path) for r in transport.requests]
    assert methods == [
        ("GET", b"/projects"),
        ("GET", b"/projects/p%2F1"),
        ("POST", b"/projects"),
        ("PATCH", b"/projects/p%2F1"),
        ("DELETE", b"/projects/p%2F1"),
    ]
    assert json.loads(transport.requests[3].content) == {"model": None}
    assert listing.projects[0].id == "p/1"


MEMORY = {
    "id": "m/1",
    "text": "Likes tea",
    "created_at": "2026-11-17T00:00:00Z",
    "updated_at": "2026-11-17T00:00:00Z",
}


def test_memory_requests() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"memories": [MEMORY]})

    client, transport = make_client(respond)

    with client:
        listing = client.list_memories()
        client.delete_memory("m/1")

    methods = [(r.method, r.url.raw_path) for r in transport.requests]
    assert methods == [("GET", b"/memories"), ("DELETE", b"/memories/m%2F1")]
    assert listing.memories[0].text == "Likes tea"
