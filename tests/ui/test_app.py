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
from agent_service.ui.sidebar_view import clear_thread_list_cache

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


INFO = {
    "agents": [
        {"key": "chatbot", "description": "Simple chatbot", "config_schema": {}},
        {"key": "research", "description": "Searches the web", "config_schema": {}},
    ],
    "models": ["fake", "gpt-test"],
    "default_agent": "chatbot",
    "default_model": "fake",
}


class FakeService:
    """Transport tiruan: `/info` selalu dijawab, request lain direkam lalu dijawab `respond`."""

    def __init__(
        self, respond: Callable[[httpx.Request], httpx.Response], info_status: int = 200
    ) -> None:
        self.requests: list[httpx.Request] = []
        self.thread_list_requests: list[httpx.Request] = []
        self.threads: list[dict[str, str]] = []
        self._respond = respond
        self._info_status = info_status

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/info":
            return httpx.Response(self._info_status, json=INFO)
        if request.method == "GET" and request.url.path.endswith("/threads"):
            self.thread_list_requests.append(request)
            return httpx.Response(200, json={"threads": self.threads})
        self.requests.append(request)
        return self._respond(request)

    def bodies(self) -> list[dict[str, object]]:
        return [json.loads(request.content) for request in self.requests]


@pytest.fixture
def clients() -> Iterator[list[AgentClient]]:
    clear_thread_list_cache()
    created: list[AgentClient] = []
    yield created
    for client in created:
        client.close()


def start_app(
    service: FakeService,
    clients: list[AgentClient],
    query_params: dict[str, str] | None = None,
) -> AppTest:
    client = AgentClient(transport=httpx.MockTransport(service.handle))
    clients.append(client)
    app = AppTest.from_file(APP_FILE, default_timeout=10)
    app.query_params.update(query_params or {})
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


def test_app_renders_without_running_agent(clients: list[AgentClient]) -> None:
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


HISTORY = {
    "messages": [{"type": "human", "content": "Lama"}, {"type": "ai", "content": "Jawaban lama"}]
}


def test_ids_are_written_to_url_after_first_message(clients: list[AgentClient]) -> None:
    service = FakeService(
        lambda request: httpx.Response(200, text=ANSWER_STREAM, headers=ID_HEADERS)
    )
    app = start_app(service, clients)
    generated_user = session_of(app).user_id

    send(app, "Hai")

    assert app.query_params["thread_id"] == "t1"
    assert app.query_params["user_id"] == "u1"
    assert service.bodies()[0]["user_id"] == generated_user


def test_user_id_from_url_is_used_for_requests(clients: list[AgentClient]) -> None:
    service = FakeService(
        lambda request: httpx.Response(200, text=ANSWER_STREAM, headers=ID_HEADERS)
    )
    app = start_app(service, clients, {"user_id": "from-url"})

    send(app, "Hai")

    assert service.bodies()[0]["user_id"] == "from-url"


def test_thread_in_url_loads_history_once(clients: list[AgentClient]) -> None:
    service = FakeService(lambda request: httpx.Response(200, json=HISTORY))
    app = start_app(service, clients, {"user_id": "u1", "thread_id": "t1", "agent": "chatbot"})

    app.run()

    [history_request] = service.requests
    assert history_request.url.path == "/chatbot/history"
    assert json.loads(history_request.content) == {"thread_id": "t1", "user_id": "u1"}
    assert [m.value for m in app.markdown] == ["Lama", "Jawaban lama"]


def test_missing_thread_in_url_starts_new_chat(clients: list[AgentClient]) -> None:
    service = FakeService(
        lambda request: httpx.Response(404, json={"detail": "Thread 't1' not found"})
    )

    app = start_app(service, clients, {"user_id": "u1", "thread_id": "t1"})

    assert "was not found" in app.warning[0].value
    assert session_of(app).thread_id is None
    assert "thread_id" not in app.query_params


def test_unreachable_service_keeps_thread_and_retries(clients: list[AgentClient]) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    service = FakeService(refuse, info_status=503)
    app = start_app(service, clients, {"user_id": "u1", "thread_id": "t1"})
    app.run()

    assert "Cannot reach the agent service" in app.error[0].value
    assert session_of(app).thread_id == "t1"
    assert len(service.requests) == 2


def stream_service() -> FakeService:
    return FakeService(lambda request: httpx.Response(200, text=ANSWER_STREAM, headers=ID_HEADERS))


def test_sidebar_shows_agents_models_and_default_selection(clients: list[AgentClient]) -> None:
    app = start_app(stream_service(), clients)

    agent_picker = app.sidebar.selectbox(key="sidebar_agent")
    model_picker = app.sidebar.selectbox(key="sidebar_model")
    assert agent_picker.options == ["chatbot", "research"]
    assert agent_picker.value == "chatbot"
    assert model_picker.value == "fake"
    assert app.sidebar.caption[0].value == "Simple chatbot"


def test_choosing_agent_starts_new_thread_on_that_agent(clients: list[AgentClient]) -> None:
    service = stream_service()
    app = start_app(service, clients)
    send(app, "Hai")

    app.sidebar.selectbox(key="sidebar_agent").set_value("research").run()
    send(app, "Cari")

    assert session_of(app).messages[0].content == "Cari"
    assert app.query_params["agent"] == "research"
    last = service.requests[-1]
    assert last.url.path == "/research/stream"
    assert "thread_id" not in json.loads(last.content)


def test_model_and_stream_toggle_are_sent_with_message(clients: list[AgentClient]) -> None:
    service = stream_service()
    app = start_app(service, clients)

    app.sidebar.selectbox(key="sidebar_model").set_value("gpt-test").run()
    app.sidebar.toggle(key="sidebar_stream_tokens").set_value(False).run()
    send(app, "Hai")

    body = service.bodies()[0]
    assert (body["model"], body["stream_tokens"]) == ("gpt-test", False)


def test_new_chat_clears_conversation(clients: list[AgentClient]) -> None:
    app = start_app(stream_service(), clients)
    send(app, "Hai")

    app.sidebar.button(key="sidebar_new_chat").click().run()

    assert session_of(app).messages == []
    assert session_of(app).thread_id is None
    assert "thread_id" not in app.query_params


def test_unknown_agent_in_url_falls_back_to_default(clients: list[AgentClient]) -> None:
    service = stream_service()
    app = start_app(service, clients, {"agent": "ghost"})
    assert "'ghost' is not available" in app.sidebar.warning[0].value

    send(app, "Hai")

    assert service.requests[-1].url.path == "/stream"
    assert "agent" not in app.query_params


def test_info_failure_hides_pickers(clients: list[AgentClient]) -> None:
    app = start_app(FakeService(lambda request: httpx.Response(200), info_status=503), clients)

    assert "Agent service unavailable" in app.sidebar.caption[0].value
    assert len(app.sidebar.selectbox) == 0


def thread(thread_id: str, title: str) -> dict[str, str]:
    return {"thread_id": thread_id, "agent_id": "chatbot", "title": title}


def test_sidebar_lists_threads_of_user_and_agent(clients: list[AgentClient]) -> None:
    service = stream_service()
    service.threads = [thread("t1", "Rencana liburan"), thread("t2", "Resep")]

    app = start_app(service, clients, {"user_id": "u1"})

    labels = [
        button.label
        for button in app.sidebar.button
        if (button.key or "").startswith("sidebar_open_")
    ]
    assert labels == ["Rencana liburan", "Resep"]
    params = dict(service.thread_list_requests[0].url.params)
    assert params == {"user_id": "u1", "limit": "20"}


def test_empty_thread_list_shows_hint(clients: list[AgentClient]) -> None:
    app = start_app(stream_service(), clients)

    assert "No conversations yet." in [caption.value for caption in app.sidebar.caption]


def test_clicking_thread_opens_its_history(clients: list[AgentClient]) -> None:
    service = FakeService(lambda request: httpx.Response(200, json=HISTORY))
    service.threads = [thread("t9", "Lama")]
    app = start_app(service, clients, {"user_id": "u1"})

    app.sidebar.button(key="sidebar_open_t9").click().run()

    assert session_of(app).thread_id == "t9"
    assert [m.value for m in app.markdown] == ["Lama", "Jawaban lama"]
    assert app.query_params["thread_id"] == "t9"
    assert app.sidebar.button(key="sidebar_open_t9").proto.type == "primary"


def test_thread_list_is_cached_until_new_thread(clients: list[AgentClient]) -> None:
    service = stream_service()
    app = start_app(service, clients, {"user_id": "u-cache"})
    app.run()
    assert len(service.thread_list_requests) == 1

    send(app, "Hai")

    assert len(service.thread_list_requests) == 2


def test_failed_open_shows_toast(clients: list[AgentClient]) -> None:
    service = FakeService(
        lambda request: httpx.Response(404, json={"detail": "Thread 't9' not found"})
    )
    service.threads = [thread("t9", "Hilang")]
    app = start_app(service, clients, {"user_id": "u-toast"})

    app.sidebar.button(key="sidebar_open_t9").click().run()

    assert "Could not open the conversation" in app.toast[0].value
    assert session_of(app).thread_id is None


def thread_service(respond: Callable[[httpx.Request], httpx.Response]) -> FakeService:
    service = FakeService(respond)
    service.threads = [thread("t1", "Judul lama"), thread("t2", "Lain")]
    return service


def test_rename_sends_trimmed_title_and_refreshes_list(clients: list[AgentClient]) -> None:
    service = thread_service(lambda request: httpx.Response(200, json=thread("t1", "Judul baru")))
    app = start_app(service, clients, {"user_id": "u-rename"})
    lists_before = len(service.thread_list_requests)

    app.text_input(key="sidebar_title_t1").set_value("  Judul baru  ")
    app.button(key="sidebar_rename_t1").click().run()

    [rename] = service.requests
    assert (rename.method, rename.url.path) == ("PATCH", "/threads/t1")
    assert json.loads(rename.content) == {"user_id": "u-rename", "title": "Judul baru"}
    assert app.toast[0].value == "Conversation renamed."
    assert len(service.thread_list_requests) == lists_before + 1


def test_empty_title_is_rejected_without_request(clients: list[AgentClient]) -> None:
    service = thread_service(lambda request: httpx.Response(500))
    app = start_app(service, clients, {"user_id": "u-empty"})

    app.text_input(key="sidebar_title_t1").set_value("   ")
    app.button(key="sidebar_rename_t1").click().run()

    assert service.requests == []
    assert app.toast[0].value == "Title cannot be empty."


def test_failed_rename_shows_error(clients: list[AgentClient]) -> None:
    service = thread_service(
        lambda request: httpx.Response(404, json={"detail": "Thread 't1' not found"})
    )
    app = start_app(service, clients, {"user_id": "u-rename-fail"})

    app.button(key="sidebar_rename_t1").click().run()

    assert "Could not rename the conversation" in app.toast[0].value


def test_delete_active_thread_starts_new_chat(clients: list[AgentClient]) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json=HISTORY)

    service = thread_service(respond)
    app = start_app(service, clients, {"user_id": "u-del", "thread_id": "t1"})
    assert session_of(app).thread_id == "t1"

    app.button(key="sidebar_delete_t1").click().run()

    delete = service.requests[-1]
    assert (delete.method, delete.url.path) == ("DELETE", "/threads/t1")
    assert dict(delete.url.params) == {"user_id": "u-del"}
    assert session_of(app).thread_id is None
    assert "thread_id" not in app.query_params
    assert app.toast[0].value == "Conversation deleted."


def test_delete_other_thread_keeps_current_chat(clients: list[AgentClient]) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json=HISTORY)

    service = thread_service(respond)
    app = start_app(service, clients, {"user_id": "u-del2", "thread_id": "t1"})

    app.button(key="sidebar_delete_t2").click().run()

    assert session_of(app).thread_id == "t1"


def test_failed_delete_shows_error(clients: list[AgentClient]) -> None:
    service = thread_service(lambda request: httpx.Response(503, json={"detail": "down"}))
    app = start_app(service, clients, {"user_id": "u-del-fail"})

    app.button(key="sidebar_delete_t1").click().run()

    assert "Could not delete the conversation" in app.toast[0].value


def test_reasoning_frames_show_thinking_block_and_are_kept(clients: list[AgentClient]) -> None:
    body = sse(
        {"type": "reasoning", "content": "Pilih "},
        {"type": "reasoning", "content": "dua warna"},
        {"type": "token", "content": "Merah"},
        {
            "type": "message",
            "content": {"type": "ai", "content": "Merah", "reasoning": "Pilih dua warna"},
        },
    )
    service = FakeService(lambda request: httpx.Response(200, text=body, headers=ID_HEADERS))
    app = start_app(service, clients)

    send(app, "Satu warna?")
    app.run()

    [status] = app.status
    assert status.markdown[0].value == "Pilih dua warna"
    assert session_of(app).messages[-1].reasoning == "Pilih dua warna"
