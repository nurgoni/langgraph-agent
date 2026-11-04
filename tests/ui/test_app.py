from pathlib import Path

import httpx
from streamlit.testing.v1 import AppTest

import agent_service.ui.app
from agent_service.client import AgentClient
from agent_service.ui.app import APP_TITLE, CLIENT_OVERRIDE_KEY

APP_FILE = str(Path(agent_service.ui.app.__file__))


def test_app_renders_title_without_calling_service() -> None:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500)

    app = AppTest.from_file(APP_FILE)
    app.session_state[CLIENT_OVERRIDE_KEY] = AgentClient(transport=httpx.MockTransport(record))

    app.run()

    assert not app.exception
    assert app.title[0].value == APP_TITLE
    assert requests == []
