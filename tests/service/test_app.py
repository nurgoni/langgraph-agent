import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from agent_service.agents.base import AgentGraph, Checkpointer
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.agents.registry import AgentRegistry
from agent_service.agents.tools.web_search import FirecrawlSearch, UnconfiguredSearch
from agent_service.core.settings import Settings
from agent_service.service.app import (
    DefaultAgentNotRegisteredError,
    build_search_backend,
    create_app,
)


class BrokenAgent(ChatbotAgent):
    def build(self, model: BaseChatModel, checkpointer: Checkpointer) -> AgentGraph:
        raise ValueError("cannot build")


def test_create_app_has_no_registry_before_lifespan(app: FastAPI) -> None:
    assert not hasattr(app.state, "registry")


def test_unknown_default_agent_is_rejected(settings: Settings) -> None:
    with pytest.raises(DefaultAgentNotRegisteredError):
        create_app(settings, default_agent_id="missing")


async def test_lifespan_loads_agents_and_creates_database(app: FastAPI, settings: Settings) -> None:
    async with app.router.lifespan_context(app):
        registry = app.state.registry
        assert isinstance(registry, AgentRegistry)
        assert registry.is_available("chatbot")
        assert Path(settings.sqlite_db_path).exists()


async def test_failed_agent_does_not_stop_startup(settings: Settings) -> None:
    agents = [ChatbotAgent(), BrokenAgent(agent_id="broken", description="Broken")]
    app = create_app(settings, agents=agents)

    async with app.router.lifespan_context(app):
        assert app.state.registry.is_available("chatbot")
        assert not app.state.registry.is_available("broken")


async def test_missing_auth_secret_logs_warning(
    app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        async with app.router.lifespan_context(app):
            pass

    assert "AUTH_SECRET is not set" in caplog.text


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
