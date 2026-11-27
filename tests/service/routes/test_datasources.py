"""`GET /datasources` dan `ProjectSettings.data_source_ids` lewat API (FR-51)."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.store.base import BaseStore

from agent_service.agents.base import AgentGraph, BaseAgent, Checkpointer
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.core.settings import Settings
from agent_service.memory.users import UserRecord
from agent_service.schema.datasources import DataSourceList
from agent_service.schema.projects import Project
from agent_service.service.app import create_app

REGISTRY_YAML = """\
data_sources:
  - id: shop
    description: Store orders
    url_env: TEST_SHOP_URL
  - id: sensors
    description: Sensor readings
    url_env: TEST_SENSORS_URL
  - id: offline
    description: Not configured
    url_env: TEST_OFFLINE_URL
"""


class DataSourceEchoAgent(BaseAgent):
    """Membalas dengan data source project dari `configurable`."""

    def build(
        self, model: BaseChatModel, checkpointer: Checkpointer, store: BaseStore | None = None
    ) -> AgentGraph:
        async def reply(state: MessagesState, config: RunnableConfig) -> dict[str, list[AIMessage]]:
            ids = config["configurable"].get("project_data_source_ids")
            return {"messages": [AIMessage(content=str(ids))]}

        # pyrefly tidak mengenali TypedDict sebagai TypedDictLike milik LangGraph.
        builder = StateGraph(MessagesState)  # pyrefly: ignore[bad-specialization]
        builder.add_node("reply", reply)
        builder.add_edge(START, "reply")
        builder.add_edge("reply", END)
        return builder.compile(checkpointer=checkpointer)


@pytest.fixture
async def data_client(
    database_url: str,
    demo_database_urls: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, FastAPI]]:
    registry_file = tmp_path / "datasources.yaml"
    registry_file.write_text(REGISTRY_YAML, encoding="utf-8")
    monkeypatch.setenv("TEST_SHOP_URL", demo_database_urls["shop"])
    monkeypatch.setenv("TEST_SENSORS_URL", demo_database_urls["sensors"])
    monkeypatch.delenv("TEST_OFFLINE_URL", raising=False)
    settings = Settings(
        _env_file=None,
        use_fake_model=True,
        database_url=database_url,
        data_sources_file=registry_file,
    )
    echo = DataSourceEchoAgent(agent_id="echo", description="Echoes project data sources")
    app = create_app(settings, agents=[ChatbotAgent(), echo], builtin_projects=[])
    async with app.router.lifespan_context(app):
        user = UserRecord(user_id="user-a", username="user-a", password_hash="", role="user")
        token = app.state.authenticator.issue_token(user).access_token
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            yield client, app


async def test_datasources_lists_status_without_connection_details(
    data_client: tuple[AsyncClient, FastAPI], demo_database_urls: dict[str, str]
) -> None:
    client, _ = data_client

    response = await client.get("/datasources")

    assert response.status_code == 200
    listing = DataSourceList.model_validate(response.json())
    assert [(s.id, s.available) for s in listing.data_sources] == [
        ("shop", True),
        ("sensors", True),
        ("offline", False),
    ]
    assert listing.data_sources[2].error == "Environment variable TEST_OFFLINE_URL is not set."
    for url in demo_database_urls.values():
        assert url.split("@")[0] not in response.text


async def test_datasources_need_a_token(anonymous_client: AsyncClient) -> None:
    assert (await anonymous_client.get("/datasources")).status_code == 401


async def test_project_data_sources_are_validated_and_reach_the_run(
    data_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, _ = data_client
    body = {"name": "Analysis", "base_agent_id": "echo", "settings": {"data_source_ids": ["shop"]}}

    created = await client.post("/projects", json=body)
    project = Project.model_validate(created.json())
    reply = await client.post(f"/projects/{project.id}/invoke", json={"message": "hi"})

    assert created.status_code == 201
    assert project.settings.data_source_ids == ["shop"]
    assert reply.json()["content"] == "['shop']"


async def test_unknown_data_sources_are_rejected_on_create_and_update(
    data_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, _ = data_client
    unknown = {"data_source_ids": ["missing"]}

    created = await client.post(
        "/projects", json={"name": "A", "base_agent_id": "echo", "settings": unknown}
    )
    project = await client.post("/projects", json={"name": "B", "base_agent_id": "echo"})
    patched = await client.patch(f"/projects/{project.json()['id']}", json={"settings": unknown})

    assert created.status_code == 422
    assert "Unknown data sources: ['missing']" in created.text
    assert patched.status_code == 422


async def test_unavailable_but_registered_data_source_can_be_chosen(
    data_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, _ = data_client
    body = {"name": "Later", "base_agent_id": "echo", "settings": {"data_source_ids": ["offline"]}}

    response = await client.post("/projects", json=body)

    assert response.status_code == 201


async def test_agent_routes_have_no_data_sources(data_client: tuple[AsyncClient, FastAPI]) -> None:
    client, _ = data_client

    response = await client.post("/echo/invoke", json={"message": "hi"})

    assert response.json()["content"] == "None"
