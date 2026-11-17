"""Smoke test end-to-end stack Docker Compose: Postgres, migrasi, service + UI, FakeModel.

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

from agent_service.client import AgentClient, AgentClientError
from agent_service.llm.fake import DEFAULT_FAKE_RESPONSE
from agent_service.schema.stream import MessageEvent, TokenEvent

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_NAME = "agent-service-e2e"
E2E_JWT_SECRET = "e2e-jwt-secret-with-at-least-32-characters"
BUILD_TIMEOUT_SECONDS = 900
COMMAND_TIMEOUT_SECONDS = 120
USERNAME = "e2e-user"
OTHER_USERNAME = "e2e-other"
PASSWORD = "e2e-password"

UI_CHAT_SCRIPT = f"""
import json
from streamlit.testing.v1 import AppTest

app = AppTest.from_file("/app/src/agent_service/ui/app.py", default_timeout=60)
app.run()
app.text_input(key="login_username").set_value("{USERNAME}")
app.text_input(key="login_password").set_value("{PASSWORD}")
app.button[0].click().run()
app.chat_input[0].set_value("Halo dari e2e").run()
print(json.dumps({{
    "exceptions": [str(item.value) for item in app.exception],
    "blocks": [block.name for block in app.chat_message],
    "reply": app.markdown[-1].value,
}}))
"""

# Setiap image hanya membawa extra miliknya (FR-31): modul ini tidak boleh ada di image tersebut.
# `uvicorn` tidak dicek di image UI, karena Streamlit 1.66 sendiri bergantung padanya.
FORBIDDEN_MODULES = {
    "agent-service": ["streamlit", "pyarrow", "pandas"],
    "ui": ["langgraph", "langchain_core", "fastapi"],
}
INSTALLED_MODULES_SCRIPT = """
import importlib.util, json, sys
print(json.dumps([name for name in sys.argv[1:] if importlib.util.find_spec(name)]))
"""


@dataclass
class ComposeStack:
    """Stack yang sedang berjalan, beserta cara menjalankan perintah compose terhadapnya."""

    service_url: str
    ui_url: str
    env: dict[str, str] = field(default_factory=dict)

    def compose(
        self, *args: str, timeout: int = COMMAND_TIMEOUT_SECONDS, stdin: str | None = None
    ) -> str:
        command = ["docker", "compose", "-p", PROJECT_NAME, *args]
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=self.env,
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            pytest.fail(f"{' '.join(command)} failed:\n{result.stdout}\n{result.stderr}")
        return result.stdout

    def create_user(self, username: str) -> None:
        """Buat akun lewat perintah operator di container service (FR-33)."""
        manage = ["python", "-m", "agent_service.manage", "create-user", username]
        self.compose("exec", "-T", "agent-service", *manage, "--password-stdin", stdin=PASSWORD)

    def client(self, username: str = USERNAME) -> AgentClient:
        client = AgentClient(self.service_url)
        client.login(username, PASSWORD)
        return client


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def stack() -> Iterator[ComposeStack]:
    if shutil.which("docker") is None:
        pytest.skip("docker is not installed")
    service_port, ui_port, postgres_port = free_port(), free_port(), free_port()
    env = {
        **os.environ,
        "SERVICE_PORT": str(service_port),
        "UI_PORT": str(ui_port),
        # Port acak supaya tidak bentrok dengan `docker compose up -d postgres` milik dev.
        "POSTGRES_PORT": str(postgres_port),
        "JWT_SECRET": E2E_JWT_SECRET,
    }
    running = ComposeStack(
        service_url=f"http://127.0.0.1:{service_port}",
        ui_url=f"http://127.0.0.1:{ui_port}",
        env=env,
    )
    try:
        running.compose("up", "-d", "--build", "--wait", timeout=BUILD_TIMEOUT_SECONDS)
        running.create_user(USERNAME)
        running.create_user(OTHER_USERNAME)
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
        reply = client.invoke("Halo")
        with client.stream("Lagi", thread_id=reply.thread_id) as run:
            events = list(run)
        history = client.get_history(reply.thread_id)

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
        reply = client.invoke("Simpan aku")

    stack.compose("restart", "agent-service")
    stack.compose("up", "-d", "--wait", "agent-service")

    with stack.client() as client:
        threads = client.get_threads()
    assert reply.thread_id in [thread.thread_id for thread in threads.threads]


@pytest.mark.parametrize(("compose_service", "modules"), FORBIDDEN_MODULES.items())
def test_image_ships_only_its_extra(
    stack: ComposeStack, compose_service: str, modules: list[str]
) -> None:
    output = stack.compose(
        "exec", "-T", compose_service, "python", "-c", INSTALLED_MODULES_SCRIPT, *modules
    )

    assert json.loads(output.strip().splitlines()[-1]) == []


def test_migrate_finished_before_service_started(stack: ComposeStack) -> None:
    output = stack.compose("ps", "--all", "--format", "json", "migrate")

    [migrate] = [json.loads(line) for line in output.strip().splitlines()]
    assert (migrate["State"], migrate["ExitCode"]) == ("exited", 0)


def test_other_user_cannot_read_thread(stack: ComposeStack) -> None:
    with stack.client() as owner:
        reply = owner.invoke("Rahasia")

    with stack.client(OTHER_USERNAME) as other, pytest.raises(AgentClientError) as error_info:
        other.get_history(reply.thread_id)

    assert error_info.value.status_code == 404


def test_builtin_skills_ship_in_the_service_image(stack: ComposeStack) -> None:
    with stack.client() as client:
        skills = client.list_skills()
        notes = client.get_skill("builtin/meeting-notes")

    assert [skill.id for skill in skills.skills] == [
        "builtin/meeting-notes",
        "builtin/research-report",
    ]
    assert notes.body.startswith("# Meeting notes")
