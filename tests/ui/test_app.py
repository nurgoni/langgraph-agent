import json
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

import agent_service.ui.app
from agent_service.client import AgentClient
from agent_service.schema.headers import THREAD_ID_HEADER, USER_ID_HEADER
from agent_service.ui.app import APP_TITLE, CLIENT_OVERRIDE_KEY
from agent_service.ui.session import SESSION_STATE_KEY, ChatSession

APP_FILE = str(Path(agent_service.ui.app.__file__))
ID_HEADERS = {THREAD_ID_HEADER: "t1", USER_ID_HEADER: "u1"}


def sse(*frames: dict[str, object]) -> str:
    body = "".join(f"data: {json.dumps(frame)}\n\n" for frame in frames)
    return body + "data: [DONE]\n\n"


ANSWER_STREAM = sse(
    {"type": "token", "content": "Hal"},
    {"type": "token", "content": "o!"},
    {"type": "message", "content": {"type": "ai", "content": "Halo!"}},
)


class FakeService:
    """Transport tiruan yang merekam request dan menjawab `/stream` dengan body tetap."""

    def __init__(self, respond: Callable[[httpx.Request], httpx.Response]) -> None:
        self.requests: list[httpx.Request] = []
        self._respond = respond

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._respond(request)

    def bodies(self) -> list[dict[str, object]]:
        return [json.loads(request.content) for request in self.requests]


@pytest.fixture
def clients() -> Iterator[list[AgentClient]]:
    created: list[AgentClient] = []
    yield created
    for client in created:
        client.close()


def start_app(service: FakeService, clients: list[AgentClient]) -> AppTest:
    client = AgentClient(transport=httpx.MockTransport(service.handle))
    clients.append(client)
    app = AppTest.from_file(APP_FILE)
    app.session_state[CLIENT_OVERRIDE_KEY] = client
    app.run()
    assert not app.exception, app.exception
    return app


def send(app: AppTest, message: str) -> None:
    app.chat_input[0].set_value(message).run()
    assert not app.exception, app.exception


def session_of(app: AppTest) -> ChatSession:
    session = app.session_state[SESSION_STATE_KEY]
    assert isinstance(session, ChatSession)
    return session


def test_app_renders_title_without_calling_service(clients: list[AgentClient]) -> None:
    service = FakeService(lambda request: httpx.Response(500))

    app = start_app(service, clients)

    assert app.title[0].value == APP_TITLE
    assert service.requests == []


def test_message_is_streamed_and_kept_in_session(clients: list[AgentClient]) -> None:
    service = FakeService(
        lambda request: httpx.Response(200, text=ANSWER_STREAM, headers=ID_HEADERS)
    )
    app = start_app(service, clients)

    send(app, "Hai")

    assert [block.name for block in app.chat_message] == ["human", "ai"]
    assert app.markdown[-1].value == "Halo!"
    session = session_of(app)
    assert (session.thread_id, session.user_id) == ("t1", "u1")
    assert [(m.type, m.content) for m in session.messages] == [("human", "Hai"), ("ai", "Halo!")]
    assert service.bodies()[0]["stream_tokens"] is True


def test_second_message_continues_same_thread(clients: list[AgentClient]) -> None:
    service = FakeService(
        lambda request: httpx.Response(200, text=ANSWER_STREAM, headers=ID_HEADERS)
    )
    app = start_app(service, clients)

    send(app, "Pertama")
    send(app, "Kedua")

    first, second = service.bodies()
    assert "thread_id" not in first
    assert (second["thread_id"], second["user_id"]) == ("t1", "u1")
    assert [block.name for block in app.chat_message] == ["human", "ai", "human", "ai"]


def test_tool_call_is_shown_as_status(clients: list[AgentClient]) -> None:
    body = sse(
        {
            "type": "message",
            "content": {
                "type": "ai",
                "content": "",
                "tool_calls": [{"name": "calculator", "args": {"x": 1}, "id": "c1"}],
            },
        },
        {"type": "message", "content": {"type": "tool", "content": "2", "tool_call_id": "c1"}},
        {"type": "message", "content": {"type": "ai", "content": "Hasilnya 2."}},
    )
    service = FakeService(lambda request: httpx.Response(200, text=body, headers=ID_HEADERS))
    app = start_app(service, clients)

    send(app, "Hitung")

    [status] = app.status
    assert "calculator" in status.label
    assert status.state == "complete"


def test_error_frame_is_shown_and_partial_answer_kept(clients: list[AgentClient]) -> None:
    body = sse({"type": "error", "content": "Internal server error"})
    service = FakeService(lambda request: httpx.Response(200, text=body, headers=ID_HEADERS))
    app = start_app(service, clients)

    send(app, "Hai")

    assert app.error[0].value == "Internal server error"
    assert [m.type for m in session_of(app).messages] == ["human"]


def test_rejected_request_shows_error_and_is_not_saved(clients: list[AgentClient]) -> None:
    service = FakeService(
        lambda request: httpx.Response(404, json={"detail": "Thread 't1' not found"})
    )
    app = start_app(service, clients)

    send(app, "Hai")

    assert "Thread 't1' not found" in app.error[0].value
    assert session_of(app).messages == []


def test_history_is_replayed_on_rerun(clients: list[AgentClient]) -> None:
    service = FakeService(
        lambda request: httpx.Response(200, text=ANSWER_STREAM, headers=ID_HEADERS)
    )
    app = start_app(service, clients)
    send(app, "Hai")

    app.run()

    assert [block.name for block in app.chat_message] == ["human", "ai"]
    assert len(service.requests) == 1


def test_unreachable_service_shows_how_to_start_it(clients: list[AgentClient]) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("[WinError 10061] connection refused", request=request)

    app = start_app(FakeService(refuse), clients)

    send(app, "Hai")

    message = app.error[0].value
    assert "Cannot reach the agent service at http://localhost:8080" in message
    assert "agent_service.run_service" in message
    assert session_of(app).messages == []


def test_broken_stream_is_not_reported_as_unreachable(clients: list[AgentClient]) -> None:
    body = 'data: {"type": "token", "content": "Hal"}\n\n'
    service = FakeService(lambda request: httpx.Response(200, text=body, headers=ID_HEADERS))
    app = start_app(service, clients)

    send(app, "Hai")

    message = app.error[0].value
    assert "Stream ended before [DONE]" in message
    assert "Cannot reach" not in message
