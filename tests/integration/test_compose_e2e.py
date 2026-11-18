"""Smoke test end-to-end stack Docker Compose: Postgres, migrasi, service + UI, FakeModel.

Dijalankan manual atau di CI: `uv run pytest -m integration`. Butuh Docker dengan Compose v2.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
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
HTTP_TIMEOUT_SECONDS = 10
USERNAME = "e2e-user"
OTHER_USERNAME = "e2e-other"
EVAL_USERNAME = "e2e-evals"
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
    web_url: str
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

    def client(self, username: str = USERNAME, base_url: str | None = None) -> AgentClient:
        client = AgentClient(base_url or self.service_url)
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
    service_port, ui_port, web_port = free_port(), free_port(), free_port()
    postgres_port = free_port()
    env = {
        **os.environ,
        "SERVICE_PORT": str(service_port),
        "UI_PORT": str(ui_port),
        "WEB_PORT": str(web_port),
        # Port acak supaya tidak bentrok dengan `docker compose up -d postgres` milik dev.
        "POSTGRES_PORT": str(postgres_port),
        "JWT_SECRET": E2E_JWT_SECRET,
    }
    running = ComposeStack(
        service_url=f"http://127.0.0.1:{service_port}",
        ui_url=f"http://127.0.0.1:{ui_port}",
        web_url=f"http://127.0.0.1:{web_port}",
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


def test_memory_store_is_migrated(stack: ComposeStack) -> None:
    with stack.client() as client:
        memories = client.list_memories()

    assert memories.memories == []


def test_runs_are_traced(stack: ComposeStack) -> None:
    with stack.client() as client:
        reply = client.invoke("Halo")
        trace = client.get_run_trace(reply.message.run_id or "")

    assert (trace.status, [span.kind for span in trace.spans]) == ("ok", ["model"])


def test_smoke_eval_cli_against_the_stack(stack: ComposeStack, tmp_path: Path) -> None:
    stack.create_user(EVAL_USERNAME)
    env = {
        **os.environ,
        "AGENT_URL": stack.service_url,
        "EVAL_USERNAME": EVAL_USERNAME,
        "EVAL_PASSWORD": PASSWORD,
    }
    command = [sys.executable, "-m", "agent_service.run_evals", "evals/smoke.yaml"]

    result = subprocess.run(
        [*command, "--output-dir", str(tmp_path)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=COMMAND_TIMEOUT_SECONDS,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "smoke: 2/2 passed" in result.stderr
    assert len(list(tmp_path.glob("eval-*.md"))) == 1


def test_web_serves_the_react_app(stack: ComposeStack) -> None:
    with httpx.Client(base_url=stack.web_url, timeout=HTTP_TIMEOUT_SECONDS) as http:
        index = http.get("/")
        deep_link = http.get("/projects/some-project")
        health = http.get("/healthz")

    assert index.status_code == 200
    assert '<div id="root"></div>' in index.text
    assert deep_link.text == index.text
    assert health.text == "ok\n"


def test_browser_path_through_the_web_proxy(stack: ComposeStack) -> None:
    """Login, request terautentikasi, dan SSE lewat `/api` same-origin (keputusan user F32)."""
    with stack.client(base_url=f"{stack.web_url}/api") as client:
        info = client.get_info()
        with client.stream("Halo lewat proxy", stream_tokens=True) as run:
            events = list(run)

    assert info.default_agent == "chatbot"
    assert any(isinstance(event, TokenEvent) for event in events)
    assert isinstance(events[-1], MessageEvent)


# Lebih besar dari default `client_max_body_size` nginx (1 MB), jadi membuktikan batas proxy F35.
LARGE_ARTIFACT_BYTES = 2 * 1024 * 1024


def test_artifacts_go_through_the_web_proxy_and_survive_restart(stack: ComposeStack) -> None:
    """Upload lewat proxy `/api`, volume `artifacts`, lampiran pesan, dan isolasi user (F35)."""
    content = os.urandom(LARGE_ARTIFACT_BYTES)
    with stack.client(base_url=f"{stack.web_url}/api") as client:
        artifact = client.upload_artifact(content, "report.bin")
        reply = client.invoke("Lihat lampiran", artifact_ids=[artifact.id])
        human = client.get_history(reply.thread_id).messages[0]

    stack.compose("restart", "agent-service")
    stack.compose("up", "-d", "--wait", "agent-service")

    with stack.client() as client:
        downloaded = client.download_artifact(artifact.id)
    with stack.client(OTHER_USERNAME) as other, pytest.raises(AgentClientError) as error:
        other.download_artifact(artifact.id)

    assert artifact.size == LARGE_ARTIFACT_BYTES
    assert human.artifacts == [artifact]
    assert downloaded == content
    assert error.value.status_code == 404


def test_attachments_land_in_the_thread_workspace(stack: ComposeStack) -> None:
    """Migrasi `0007` dan salinan lampiran ke workspace thread (F36)."""
    with stack.client() as client:
        artifact = client.upload_artifact(b"region,total\nnorth,10\n", "sales.csv", "text/csv")
        reply = client.invoke("Baca lampiran", artifact_ids=[artifact.id])

    query = f"SELECT path FROM workspace_files WHERE thread_id = '{reply.thread_id}'"
    user = stack.env.get("POSTGRES_USER") or "agent"
    database = stack.env.get("POSTGRES_DB") or "agent_service"
    output = stack.compose(
        "exec", "-T", "postgres", "psql", "-U", user, "-d", database, "-tAc", query
    )

    assert output.split() == ["uploads/sales.csv"]
