from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, ConfigDict

from agent_service.agents.base import AgentGraph, Checkpointer
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.core.settings import Settings
from agent_service.schema.responses import ServiceMetadata
from agent_service.service.app import create_app


class StyleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tone: str = "formal"


class StyledAgent(ChatbotAgent):
    config_schema = StyleConfig


class BrokenAgent(ChatbotAgent):
    def build(self, model: BaseChatModel, checkpointer: Checkpointer) -> AgentGraph:
        raise ValueError("cannot build")


@pytest.fixture
async def multi_agent_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        _env_file=None,
        use_fake_model=True,
        sqlite_db_path=tmp_path / "test.db",
        llm_base_url="http://llm.test/v1",
        llm_api_key="sk-test",
        available_models=["fake", "gpt-test"],
    )
    agents = [
        ChatbotAgent(),
        StyledAgent(agent_id="styled", description="Styled replies"),
        BrokenAgent(agent_id="broken", description="Never loads"),
    ]
    app = create_app(settings, agents=agents, default_agent_id="styled")
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


async def test_info_matches_service_metadata_contract(client: AsyncClient) -> None:
    response = await client.get("/info")

    assert response.status_code == 200
    metadata = ServiceMetadata.model_validate(response.json())
    assert [agent.key for agent in metadata.agents] == ["chatbot"]
    assert metadata.default_agent == "chatbot"
    assert metadata.models == ["fake"]
    assert metadata.default_model == "fake"


async def test_info_lists_only_available_agents(multi_agent_client: AsyncClient) -> None:
    metadata = ServiceMetadata.model_validate((await multi_agent_client.get("/info")).json())

    assert [agent.key for agent in metadata.agents] == ["chatbot", "styled"]
    assert metadata.default_agent == "styled"
    assert metadata.models == ["fake", "gpt-test"]


async def test_info_includes_agent_config_schema(multi_agent_client: AsyncClient) -> None:
    metadata = ServiceMetadata.model_validate((await multi_agent_client.get("/info")).json())

    styled = next(agent for agent in metadata.agents if agent.key == "styled")
    assert styled.config_schema == StyleConfig.model_json_schema()
