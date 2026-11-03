"""App factory FastAPI: membangun semua dependency service di lifespan."""

import logging
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Final

from fastapi import Depends, FastAPI

from agent_service.agents.base import BaseAgent
from agent_service.agents.catalog import DEFAULT_AGENT_ID, create_default_agents
from agent_service.agents.registry import AgentRegistry
from agent_service.core.settings import Settings
from agent_service.llm.factory import ModelFactory
from agent_service.memory.checkpointer import CheckpointerProvider
from agent_service.service.auth import verify_bearer
from agent_service.service.errors import register_exception_handlers
from agent_service.service.routes import health, history, info, invoke

logger = logging.getLogger(__name__)

APP_TITLE: Final = "Agent Service"

type Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


class DefaultAgentNotRegisteredError(ValueError):
    """Agent default tidak ada di daftar agent yang akan didaftarkan."""


def create_app(
    settings: Settings | None = None,
    agents: Sequence[BaseAgent] | None = None,
    default_agent_id: str = DEFAULT_AGENT_ID,
) -> FastAPI:
    """Bangun app FastAPI. Tidak ada koneksi atau load agent sebelum lifespan berjalan.

    Dipakai uvicorn sebagai factory (`--factory`), sehingga `Settings` dibaca saat app dibuat,
    bukan saat modul di-import.

    Args:
        settings: Konfigurasi service. Default: dibaca dari env dan `.env`.
        agents: Agent yang didaftarkan. Default: `create_default_agents()`.
        default_agent_id: Agent untuk `/info` dan route tanpa `{agent_id}`.

    Returns:
        App yang siap dijalankan.

    Raises:
        DefaultAgentNotRegisteredError: Jika `default_agent_id` tidak ada di `agents`.

    >>> app = create_app(Settings(_env_file=None, use_fake_model=True))
    >>> app.title, app.state.default_agent_id
    ('Agent Service', 'chatbot')
    """
    resolved_settings = Settings() if settings is None else settings
    resolved_agents = create_default_agents() if agents is None else list(agents)
    agent_ids = [agent.agent_id for agent in resolved_agents]
    if default_agent_id not in agent_ids:
        raise DefaultAgentNotRegisteredError(
            f"Default agent {default_agent_id!r} is not in registered agents {agent_ids}"
        )

    app = FastAPI(title=APP_TITLE, lifespan=_build_lifespan(resolved_settings, resolved_agents))
    register_exception_handlers(app)
    app.include_router(health.router)
    protected = [Depends(verify_bearer)]
    app.include_router(info.router, dependencies=protected)
    app.include_router(invoke.router, dependencies=protected)
    app.include_router(history.router, dependencies=protected)
    app.state.settings = resolved_settings
    app.state.default_agent_id = default_agent_id
    return app


def _build_lifespan(settings: Settings, agents: Sequence[BaseAgent]) -> Lifespan:
    """Buat lifespan yang membuka checkpointer, mendaftarkan, dan memuat semua agent.

    Urutan: `ModelFactory` → `CheckpointerProvider` → `AgentRegistry.load_all()`. Factory dan
    registry disimpan di `app.state`, dan checkpointer ditutup saat shutdown.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        if settings.auth_secret is None:
            logger.warning("AUTH_SECRET is not set: every endpoint is unauthenticated")
        model_factory = ModelFactory(settings)
        async with CheckpointerProvider(settings.sqlite_db_path) as checkpointer:
            registry = AgentRegistry(model_factory, checkpointer)
            for agent in agents:
                registry.register(agent)
            await registry.load_all()
            app.state.model_factory = model_factory
            app.state.registry = registry
            yield
        logger.info("Service shut down")

    return lifespan
