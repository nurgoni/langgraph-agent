"""Smoke test end-to-end stack Docker Compose: service + UI, FakeModel, tanpa API key.

Dijalankan manual atau di CI: `uv run pytest -m integration`. Butuh Docker dengan Compose v2.
"""

import json
import os
import shutil
import socket
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest

from agent_service.client import AgentClient
from agent_service.llm.fake import DEFAULT_FAKE_RESPONSE
from agent_service.schema.stream import MessageEvent, TokenEvent

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_NAME = "agent-service-e2e"
E2E_SECRET = "e2e-secret"
BUILD_TIMEOUT_SECONDS = 900
COMMAND_TIMEOUT_SECONDS = 120
OWNER = "e2e-user"

UI_CHAT_SCRIPT = """
import json
from streamlit.testing.v1 import AppTest

app = AppTest.from_file("/app/src/agent_service/ui/app.py", default_timeout=60)
app.run()
app.chat_input[0].set_value("Halo dari e2e").run()
print(json.dumps({
    "exceptions": [str(item.value) for item in app.exception],
    "blocks": [block.name for block in app.chat_message],
    "reply": app.markdown[-1].value,
}))
"""


@dataclass
class ComposeStack:
    """Stack yang sedang berjalan, beserta cara menjalankan perintah compose terhadapnya."""

    service_url: str
    ui_url: str
    env: dict[str, str] = field(default_factory=dict)

    def compose(self, *args: str, timeout: int = COMMAND_TIMEOUT_SECONDS) -> str:
        command = ["docker", "compose", "-p", PROJECT_NAME, *args]
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            pytest.fail(f"{' '.join(command)} failed:\n{result.stdout}\n{result.stderr}")
        return result.stdout

    def client(self) -> AgentClient:
        return AgentClient(self.service_url, auth_secret=E2E_SECRET)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def stack() -> Iterator[ComposeStack]:
    if shutil.which("docker") is None:
        pytest.skip("docker is not installed")
    service_port, ui_port = free_port(), free_port()
    env = {
        **os.environ,
        "SERVICE_PORT": str(service_port),
        "UI_PORT": str(ui_port),
        "AUTH_SECRET": E2E_SECRET,
    }
    running = ComposeStack(
        service_url=f"http://127.0.0.1:{service_port}",
        ui_url=f"http://127.0.0.1:{ui_port}",
        env=env,
    )
    try:
        running.compose("up", "-d", "--build", "--wait", timeout=BUILD_TIMEOUT_SECONDS)
        yield running
    finally:
        running.compose("down", "-v")


def test_service_runs_fake_model_behind_auth(stack: ComposeStack) -> None:
    with stack.client() as client:
        info = client.get_info()

    unauthorized = httpx.get(f"{stack.service_url}/info")
    assert (info.default_agent, info.default_model) == ("chatbot", "fake")
    assert unauthorized.status_code == 401


def test_conversation_over_invoke_and_stream(stack: ComposeStack) -> None:
    with stack.client() as client:
        reply = client.invoke("Halo", user_id=OWNER)
        with client.stream("Lagi", thread_id=reply.thread_id, user_id=OWNER) as run:
            events = list(run)
        history = client.get_history(reply.thread_id, OWNER)

    tokens = "".join(event.content for event in events if isinstance(event, TokenEvent))
    assert reply.message.content == DEFAULT_FAKE_RESPONSE
    assert tokens == DEFAULT_FAKE_RESPONSE
    assert any(isinstance(event, MessageEvent) for event in events)
    assert [message.type for message in history.messages] == ["human", "ai", "human", "ai"]


def test_ui_is_healthy(stack: ComposeStack) -> None:
    response = httpx.get(f"{stack.ui_url}/_stcore/health")

    assert response.text == "ok"


def test_ui_container_chats_with_service(stack: ComposeStack) -> None:
    output = stack.compose("exec", "-T", "ui", "python", "-c", UI_CHAT_SCRIPT)

    result = json.loads(output.strip().splitlines()[-1])
    assert result == {
        "exceptions": [],
        "blocks": ["human", "ai"],
        "reply": DEFAULT_FAKE_RESPONSE,
    }


def test_threads_survive_service_restart(stack: ComposeStack) -> None:
    with stack.client() as client:
        reply = client.invoke("Simpan aku", user_id=OWNER)

    stack.compose("restart", "agent-service")
    stack.compose("up", "-d", "--wait", "agent-service")

    with stack.client() as client:
        threads = client.get_threads(OWNER)
    assert reply.thread_id in [thread.thread_id for thread in threads.threads]
