from collections.abc import AsyncIterator, Callable
from typing import Any

import psycopg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.store.base import BaseStore

from agent_service.agents.base import AgentGraph, BaseAgent, Checkpointer
from agent_service.agents.catalog import BuiltinProject
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.core.settings import Settings
from agent_service.llm.reasoning import ReasoningChatOpenAI
from agent_service.memory.users import UserRecord
from agent_service.schema.projects import Project, ProjectList
from agent_service.schema.responses import ChatHistory, ChatMessage, UserThreads
from agent_service.service.app import create_app

OTHER = "user-b"
BUILTIN_ID = "general-assistant"

type AuthHeaders = Callable[..., dict[str, str]]


async def create(client: AsyncClient, **body: Any) -> Project:  # Any: body JSON
    payload = {"name": "Catatan rapat", "base_agent_id": "chatbot", **body}
    response = await client.post("/projects", json=payload)
    assert response.status_code == 201, response.text
    return Project.model_validate(response.json())


async def invoke(
    client: AsyncClient, project_id: str, headers: dict[str, str] | None = None, **body: Any
) -> ChatMessage:
    response = await client.post(
        f"/projects/{project_id}/invoke", json={"message": "Halo", **body}, headers=headers
    )
    assert response.status_code == 200, response.text
    return ChatMessage.model_validate(response.json())


# ---------------- CRUD


async def test_builtin_projects_are_seeded_when_their_agent_is_registered(
    client: AsyncClient,
) -> None:
    listing = ProjectList.model_validate((await client.get("/projects")).json())

    [builtin] = listing.projects
    assert (builtin.id, builtin.scope, builtin.read_only) == (BUILTIN_ID, "builtin", True)
    assert builtin.base_agent_id == "chatbot"


async def test_created_project_is_listed_after_builtin(client: AsyncClient) -> None:
    project = await create(
        client,
        description="Untuk rapat mingguan",
        instructions="Ringkas dalam poin.",
        skill_ids=["builtin/meeting-notes"],
        settings={"max_tokens": 512},
    )

    fetched = Project.model_validate((await client.get(f"/projects/{project.id}")).json())
    listing = ProjectList.model_validate((await client.get("/projects")).json())

    assert fetched == project
    assert (project.scope, project.read_only, project.settings.max_tokens) == ("user", False, 512)
    assert [p.id for p in listing.projects] == [BUILTIN_ID, project.id]


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ({"base_agent_id": "ghost"}, "Agent 'ghost' is not available"),
        ({"model": "gpt-x"}, "gpt-x"),
    ],
)
async def test_unknown_agent_or_model_is_422(
    client: AsyncClient, body: dict[str, str], fragment: str
) -> None:
    response = await client.post(
        "/projects", json={"name": "X", "base_agent_id": "chatbot", **body}
    )

    assert response.status_code == 422
    assert fragment in response.json()["detail"]


@pytest.mark.parametrize(
    "body",
    [
        {"name": "   "},
        {"skill_ids": ["Not Valid"]},
        {"skill_ids": ["meeting-notes"]},
        {"settings": {"max_tokens": 0}},
        {"settings": {"unknown": True}},
        {"owner_id": "someone-else"},
    ],
)
async def test_invalid_project_body_is_422(client: AsyncClient, body: dict[str, object]) -> None:
    response = await client.post(
        "/projects", json={"name": "X", "base_agent_id": "chatbot", **body}
    )

    assert response.status_code == 422


async def test_patch_changes_only_sent_fields(client: AsyncClient) -> None:
    project = await create(client, model="fake", instructions="Lama")

    response = await client.patch(
        f"/projects/{project.id}",
        json={"name": "Baru", "model": None, "settings": {"max_tokens": 64}},
    )

    updated = Project.model_validate(response.json())
    assert (updated.name, updated.model, updated.instructions) == ("Baru", None, "Lama")
    assert updated.settings.max_tokens == 64
    assert updated.updated_at >= project.updated_at


async def test_base_agent_cannot_be_changed(client: AsyncClient) -> None:
    project = await create(client)

    response = await client.patch(f"/projects/{project.id}", json={"base_agent_id": "tone"})

    assert response.status_code == 422


@pytest.mark.parametrize(("method", "body"), [("PATCH", {"name": "Dibajak"}), ("DELETE", None)])
async def test_builtin_project_is_read_only(
    client: AsyncClient, method: str, body: dict[str, str] | None
) -> None:
    response = await client.request(method, f"/projects/{BUILTIN_ID}", json=body)

    assert response.status_code == 403
    assert "read-only" in response.json()["detail"]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "", None),
        ("PATCH", "", {"name": "Dibajak"}),
        ("DELETE", "", None),
        ("POST", "/invoke", {"message": "Halo"}),
        ("POST", "/stream", {"message": "Halo"}),
        ("POST", "/history", {"thread_id": "t1"}),
        ("GET", "/threads", None),
        ("PATCH", "/threads/t1", {"title": "X"}),
        ("DELETE", "/threads/t1", None),
    ],
)
async def test_other_users_project_is_not_found(
    client: AsyncClient,
    auth_headers: AuthHeaders,
    method: str,
    path: str,
    body: dict[str, str] | None,
) -> None:
    project = await create(client)

    response = await client.request(
        method, f"/projects/{project.id}{path}", json=body, headers=auth_headers(OTHER)
    )

    assert response.status_code == 404
    assert response.json() == {"detail": f"Project {project.id!r} not found"}


async def test_other_users_do_not_see_project_in_listing(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    await create(client)

    response = await client.get("/projects", headers=auth_headers(OTHER))

    assert [p["id"] for p in response.json()["projects"]] == [BUILTIN_ID]


async def test_projects_need_a_token(anonymous_client: AsyncClient) -> None:
    assert (await anonymous_client.get("/projects")).status_code == 401


# ---------------- chat di project


async def test_thread_is_recorded_in_project_and_filtered(client: AsyncClient) -> None:
    project = await create(client)
    await invoke(client, project.id, thread_id="p-thread")
    await client.post("/chatbot/invoke", json={"message": "Tanpa project", "thread_id": "a-thread"})

    in_project = UserThreads.model_validate(
        (await client.get(f"/projects/{project.id}/threads")).json()
    )
    outside = UserThreads.model_validate((await client.get("/chatbot/threads")).json())

    assert [(t.thread_id, t.project_id) for t in in_project.threads] == [("p-thread", project.id)]
    assert [(t.thread_id, t.project_id) for t in outside.threads] == [("a-thread", None)]


async def test_project_thread_is_only_reachable_through_its_project(client: AsyncClient) -> None:
    project = await create(client)
    other_project = await create(client, name="Lain")
    await invoke(client, project.id, thread_id="t1")

    own = await client.post(f"/projects/{project.id}/history", json={"thread_id": "t1"})
    via_agent = await client.post("/chatbot/history", json={"thread_id": "t1"})
    via_other = await client.post(f"/projects/{other_project.id}/history", json={"thread_id": "t1"})
    continue_via_agent = await client.post(
        "/chatbot/invoke", json={"message": "Lanjut", "thread_id": "t1"}
    )

    assert [m.type for m in ChatHistory.model_validate(own.json()).messages] == ["human", "ai"]
    assert [via_agent.status_code, via_other.status_code, continue_via_agent.status_code] == [
        404,
        404,
        404,
    ]


async def test_agent_thread_cannot_be_moved_into_a_project(client: AsyncClient) -> None:
    project = await create(client)
    await client.post("/chatbot/invoke", json={"message": "Halo", "thread_id": "t1"})

    response = await client.post(
        f"/projects/{project.id}/invoke", json={"message": "Pindah", "thread_id": "t1"}
    )

    assert response.status_code == 404


async def test_stream_rename_and_delete_inside_project(client: AsyncClient) -> None:
    project = await create(client)
    async with client.stream(
        "POST", f"/projects/{project.id}/stream", json={"message": "Halo", "thread_id": "t1"}
    ) as response:
        lines = [line async for line in response.aiter_lines() if line]
    renamed = await client.patch(f"/projects/{project.id}/threads/t1", json={"title": "Judul"})
    deleted = await client.delete(f"/projects/{project.id}/threads/t1")
    history = await client.post(f"/projects/{project.id}/history", json={"thread_id": "t1"})

    assert lines[-1] == "data: [DONE]"
    assert (renamed.json()["title"], renamed.json()["project_id"]) == ("Judul", project.id)
    assert (deleted.status_code, history.status_code) == (204, 404)


async def test_builtin_project_threads_stay_per_user(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    await invoke(client, BUILTIN_ID, thread_id="mine")
    await invoke(client, BUILTIN_ID, headers=auth_headers(OTHER), thread_id="theirs")

    threads = UserThreads.model_validate(
        (await client.get(f"/projects/{BUILTIN_ID}/threads")).json()
    )
    peek = await client.post(f"/projects/{BUILTIN_ID}/history", json={"thread_id": "theirs"})

    assert [t.thread_id for t in threads.threads] == ["mine"]
    assert peek.status_code == 404


async def test_deleting_project_deletes_its_threads(client: AsyncClient, database_url: str) -> None:
    project = await create(client)
    await invoke(client, project.id, thread_id="t1")
    await invoke(client, project.id, thread_id="t2")
    await client.patch(f"/projects/{project.id}/threads/t1", json={"title": "Judul"})

    response = await client.delete(f"/projects/{project.id}")

    with psycopg.connect(database_url) as connection:
        checkpoints = connection.execute(
            "SELECT count(*) FROM checkpoints WHERE thread_id IN ('t1', 't2')"
        ).fetchone()
        titles = connection.execute("SELECT count(*) FROM thread_metadata").fetchone()
    assert response.status_code == 204
    assert (await client.get(f"/projects/{project.id}")).status_code == 404
    assert checkpoints == (0,)
    assert titles == (0,)


# ---------------- model, max_tokens, dan instruksi project


class RecordingAgent(BaseAgent):
    """Mencatat model yang dipakai graph, dan membalas dengan instruksi project dari config."""

    def __init__(self) -> None:
        super().__init__(agent_id="recorder", description="Records the model it is built with")
        self.models: list[BaseChatModel] = []

    def build(
        self, model: BaseChatModel, checkpointer: Checkpointer, store: BaseStore | None = None
    ) -> AgentGraph:
        self.models.append(model)

        async def reply(state: MessagesState, config: RunnableConfig) -> dict[str, list[AIMessage]]:
            configurable = config["configurable"]
            content = f"{configurable.get('project_id')}|{configurable.get('project_instructions')}"
            return {"messages": [AIMessage(content=content)]}

        # pyrefly tidak mengenali TypedDict sebagai TypedDictLike milik LangGraph.
        builder = StateGraph(MessagesState)  # pyrefly: ignore[bad-specialization]
        builder.add_node("reply", reply)
        builder.add_edge(START, "reply")
        builder.add_edge("reply", END)
        return builder.compile(checkpointer=checkpointer)


@pytest.fixture
def recorder() -> RecordingAgent:
    return RecordingAgent()


@pytest.fixture
async def model_client(
    database_url: str, recorder: RecordingAgent
) -> AsyncIterator[tuple[AsyncClient, FastAPI]]:
    settings = Settings(
        _env_file=None,
        use_fake_model=True,
        database_url=database_url,
        llm_base_url="http://llm.test/v1",
        llm_api_key="sk-test",
        default_model="fake",
        available_models=["fake", "gpt-small", "gpt-big"],
        llm_max_tokens=1000,
    )
    builtins = [BuiltinProject("builtin-recorder", "Recorder", "", "recorder", "Bawaan")]
    app = create_app(settings, agents=[ChatbotAgent(), recorder], builtin_projects=builtins)
    async with app.router.lifespan_context(app):
        user = UserRecord(user_id="user-a", username="user-a", password_hash="", role="user")
        token = app.state.authenticator.issue_token(user).access_token
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            yield client, app


def last_model(recorder: RecordingAgent) -> tuple[str, int | None]:
    model = recorder.models[-1]
    assert isinstance(model, ReasoningChatOpenAI)
    return model.model_name, model.max_tokens


@pytest.mark.parametrize(
    ("project_model", "requested_model", "expected_model"),
    [
        ("gpt-small", None, "gpt-small"),
        ("gpt-small", "gpt-big", "gpt-big"),
    ],
)
async def test_run_uses_request_then_project_model_and_project_max_tokens(
    model_client: tuple[AsyncClient, FastAPI],
    recorder: RecordingAgent,
    project_model: str,
    requested_model: str | None,
    expected_model: str,
) -> None:
    client, _ = model_client
    project = await create(
        client, base_agent_id="recorder", model=project_model, settings={"max_tokens": 321}
    )

    await invoke(client, project.id, model=requested_model)

    assert last_model(recorder) == (expected_model, 321)


async def test_project_without_overrides_uses_service_defaults(
    model_client: tuple[AsyncClient, FastAPI], recorder: RecordingAgent
) -> None:
    client, _ = model_client
    project = await create(client, base_agent_id="recorder")

    await invoke(client, project.id, model="gpt-small")

    assert last_model(recorder) == ("gpt-small", 1000)


async def test_project_instructions_reach_the_agent_and_changes_apply_next_turn(
    model_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, _ = model_client
    project = await create(client, base_agent_id="recorder", instructions="Versi 1")

    first = await invoke(client, project.id, thread_id="t1")
    await client.patch(f"/projects/{project.id}", json={"instructions": "Versi 2"})
    second = await invoke(client, project.id, thread_id="t1")

    assert first.content == f"{project.id}|Versi 1"
    assert second.content == f"{project.id}|Versi 2"


async def test_agent_routes_carry_no_project_config(
    model_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, _ = model_client

    response = await client.post("/recorder/invoke", json={"message": "Halo"})

    assert response.json()["content"] == "None|None"


async def test_custom_builtin_list_is_seeded(model_client: tuple[AsyncClient, FastAPI]) -> None:
    client, _ = model_client

    listing = ProjectList.model_validate((await client.get("/projects")).json())

    assert [(p.id, p.instructions) for p in listing.projects] == [("builtin-recorder", "Bawaan")]
