import psycopg
import pytest
from fastapi import FastAPI
from langchain_core.language_models import BaseChatModel
from langgraph.store.base import BaseStore
from pydantic import SecretStr

from agent_service.agents.base import AgentGraph, Checkpointer
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.agents.registry import AgentRegistry
from agent_service.agents.tools.web_search import FirecrawlSearch, UnconfiguredSearch
from agent_service.core.settings import Settings
from agent_service.memory.migrator import DatabaseNotMigratedError, expected_heads
from agent_service.service.app import (
    DefaultAgentNotRegisteredError,
    build_search_backend,
    create_app,
)
from agent_service.service.threads import ThreadRepository


class BrokenAgent(ChatbotAgent):
    def build(
        self, model: BaseChatModel, checkpointer: Checkpointer, store: BaseStore | None = None
    ) -> AgentGraph:
        raise ValueError("cannot build")


def test_create_app_has_no_registry_before_lifespan(app: FastAPI) -> None:
    assert not hasattr(app.state, "registry")


def test_unknown_default_agent_is_rejected(settings: Settings) -> None:
    with pytest.raises(DefaultAgentNotRegisteredError):
        create_app(settings, default_agent_id="missing")


async def test_lifespan_loads_agents_and_thread_repository(app: FastAPI) -> None:
    async with app.router.lifespan_context(app):
        registry = app.state.registry
        assert isinstance(registry, AgentRegistry)
        assert registry.is_available("chatbot")
        assert isinstance(app.state.thread_repository, ThreadRepository)


async def test_lifespan_refuses_unmigrated_database(app: FastAPI, database_url: str) -> None:
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute("UPDATE alembic_version SET version_num = 'stale'")
    try:
        with pytest.raises(DatabaseNotMigratedError):
            async with app.router.lifespan_context(app):
                pass
    finally:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute(
                "UPDATE alembic_version SET version_num = %s", list(expected_heads())
            )


async def test_failed_agent_does_not_stop_startup(settings: Settings) -> None:
    agents = [ChatbotAgent(), BrokenAgent(agent_id="broken", description="Broken")]
    app = create_app(settings, agents=agents)

    async with app.router.lifespan_context(app):
        assert app.state.registry.is_available("chatbot")
        assert not app.state.registry.is_available("broken")


def test_search_backend_follows_firecrawl_key(settings: Settings) -> None:
    configured = settings.model_copy(update={"firecrawl_api_key": SecretStr("fc-test")})

    assert isinstance(build_search_backend(settings), UnconfiguredSearch)
    assert isinstance(build_search_backend(configured), FirecrawlSearch)


async def test_default_agents_include_research_agents(settings: Settings) -> None:
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        agent_ids = {agent.agent_id for agent in app.state.registry.list_agents()}
        available = {a for a in agent_ids if app.state.registry.is_available(a)}

    assert {"research-assistant", "supervisor"} <= available
