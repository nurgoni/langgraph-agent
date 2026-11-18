"""App factory FastAPI: membangun semua dependency service di lifespan."""

import logging
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Final

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_service.agents.base import BaseAgent
from agent_service.agents.catalog import (
    BUILTIN_PROJECTS,
    DEFAULT_AGENT_ID,
    BuiltinProject,
    create_default_agents,
)
from agent_service.agents.registry import AgentRegistry
from agent_service.agents.tools.web_search import SearchBackend, create_search_backend
from agent_service.core.settings import Settings
from agent_service.files.artifacts import LocalArtifactStore
from agent_service.harness.context_policy import ContextPolicy
from agent_service.harness.skills.registry import SkillRegistry
from agent_service.harness.skills.sources import BUILTIN_SKILLS_DIR, FilesystemSkillSource
from agent_service.harness.skills.toolkit import SkillToolkit
from agent_service.llm.factory import ModelFactory
from agent_service.memory.artifacts import ArtifactRepository
from agent_service.memory.checkpointer import CheckpointerProvider
from agent_service.memory.database import DatabaseEngineProvider
from agent_service.memory.migrator import ensure_database_migrated
from agent_service.memory.projects import ProjectRepository
from agent_service.memory.store import StoreProvider
from agent_service.memory.thread_metadata import ThreadMetadataRepository
from agent_service.memory.traces import RunTraceRepository
from agent_service.memory.user_memories import UserMemoryRepository
from agent_service.memory.users import UserRepository
from agent_service.schema.headers import THREAD_ID_HEADER
from agent_service.service.artifacts import ArtifactService
from agent_service.service.auth import Authenticator
from agent_service.service.dependencies import current_principal
from agent_service.service.errors import register_exception_handlers
from agent_service.service.projects import ProjectService
from agent_service.service.routes import (
    artifacts,
    auth,
    health,
    history,
    info,
    invoke,
    memories,
    projects,
    runs,
    skills,
    stream,
    threads,
)
from agent_service.service.threads import ThreadRepository

logger = logging.getLogger(__name__)

APP_TITLE: Final = "Agent Service"
# Token dikirim lewat header Authorization, bukan cookie, jadi credentials CORS tidak dibutuhkan.
CORS_ALLOWED_METHODS: Final = ["GET", "POST", "PATCH", "DELETE"]
CORS_ALLOWED_HEADERS: Final = ["Authorization", "Content-Type"]

type Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


class DefaultAgentNotRegisteredError(ValueError):
    """Agent default tidak ada di daftar agent yang akan didaftarkan."""


def create_app(
    settings: Settings | None = None,
    agents: Sequence[BaseAgent] | None = None,
    default_agent_id: str = DEFAULT_AGENT_ID,
    builtin_projects: Sequence[BuiltinProject] = BUILTIN_PROJECTS,
    skill_registry: SkillRegistry | None = None,
) -> FastAPI:
    """Bangun app FastAPI. Tidak ada koneksi atau load agent sebelum lifespan berjalan.

    Dipakai uvicorn sebagai factory (`--factory`), sehingga `Settings` dibaca saat app dibuat,
    bukan saat modul di-import.

    Args:
        settings: Konfigurasi service. Default: dibaca dari env dan `.env`.
        agents: Agent yang didaftarkan. Default: `create_default_agents()` dengan web search
            dari `FIRECRAWL_API_KEY` dan anggaran riwayat dari `CONTEXT_MAX_TOKENS`.
        default_agent_id: Agent untuk `/info` dan route tanpa `{agent_id}`.
        builtin_projects: Project built-in yang di-seed saat startup, jika agent dasarnya
            terdaftar.
        skill_registry: Registry skill. Default: skill built-in dari folder package. File baru
            dibaca di lifespan.

    Returns:
        App yang siap dijalankan.

    Raises:
        DefaultAgentNotRegisteredError: Jika `default_agent_id` tidak ada di `agents`.

    >>> settings = Settings(_env_file=None, use_fake_model=True, jwt_secret="x" * 32)
    >>> app = create_app(settings)
    >>> app.title, app.state.default_agent_id
    ('Agent Service', 'chatbot')
    """
    resolved_settings = Settings() if settings is None else settings
    resolved_skills = default_skill_registry() if skill_registry is None else skill_registry
    if agents is None:
        resolved_agents = create_default_agents(
            build_search_backend(resolved_settings),
            SkillToolkit(resolved_skills),
            ContextPolicy(max_tokens=resolved_settings.context_max_tokens),
        )
    else:
        resolved_agents = list(agents)
    agent_ids = [agent.agent_id for agent in resolved_agents]
    if default_agent_id not in agent_ids:
        raise DefaultAgentNotRegisteredError(
            f"Default agent {default_agent_id!r} is not in registered agents {agent_ids}"
        )

    lifespan = _build_lifespan(
        resolved_settings, resolved_agents, builtin_projects, resolved_skills
    )
    app = FastAPI(title=APP_TITLE, lifespan=lifespan)
    register_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_methods=CORS_ALLOWED_METHODS,
        allow_headers=CORS_ALLOWED_HEADERS,
        expose_headers=[THREAD_ID_HEADER],
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    protected = [Depends(current_principal)]
    app.include_router(info.router, dependencies=protected)
    app.include_router(invoke.router, dependencies=protected)
    app.include_router(stream.router, dependencies=protected)
    app.include_router(history.router, dependencies=protected)
    app.include_router(threads.router, dependencies=protected)
    app.include_router(projects.router, dependencies=protected)
    app.include_router(skills.router, dependencies=protected)
    app.include_router(memories.router, dependencies=protected)
    app.include_router(runs.router, dependencies=protected)
    app.include_router(artifacts.router, dependencies=protected)
    app.state.settings = resolved_settings
    app.state.default_agent_id = default_agent_id
    return app


def default_skill_registry() -> SkillRegistry:
    """Registry berisi skill built-in dari `skills/builtin/` (belum dimuat)."""
    return SkillRegistry([FilesystemSkillSource(BUILTIN_SKILLS_DIR)])


def build_search_backend(settings: Settings) -> SearchBackend:
    """Mesin pencari untuk tool web search, dari `FIRECRAWL_API_KEY` di `Settings`.

    >>> settings = Settings(_env_file=None, use_fake_model=True, jwt_secret="x" * 32)
    >>> type(build_search_backend(settings)).__name__
    'UnconfiguredSearch'
    """
    secret = settings.firecrawl_api_key
    return create_search_backend(None if secret is None else secret.get_secret_value())


def _build_lifespan(
    settings: Settings,
    agents: Sequence[BaseAgent],
    builtin_projects: Sequence[BuiltinProject],
    skill_registry: SkillRegistry,
) -> Lifespan:
    """Buat lifespan yang membuka database, mendaftarkan, dan memuat semua agent.

    Urutan: muat skill → siapkan direktori artifact → `ModelFactory` → engine +
    `CheckpointerProvider` + `StoreProvider` → cek migrasi → `AgentRegistry.load_all()` → seed
    project built-in. Factory, registry, `ThreadRepository`, `ProjectService`, `ArtifactService`,
    `UserMemoryRepository`, `RunTraceRepository`, dan `Authenticator` disimpan di `app.state`.
    Engine dan pool checkpointer/store ditutup saat shutdown. Startup gagal jika Postgres tidak
    terjangkau atau migrasi belum dijalankan.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        await skill_registry.load()
        app.state.skill_registry = skill_registry
        artifact_store = LocalArtifactStore(settings.artifact_dir)
        await artifact_store.prepare()
        model_factory = ModelFactory(settings)
        database_url = settings.database_url.get_secret_value()
        async with (
            DatabaseEngineProvider(database_url) as engine,
            CheckpointerProvider(database_url) as checkpointer,
            StoreProvider(database_url) as store,
        ):
            await ensure_database_migrated(engine)
            titles = ThreadMetadataRepository(engine)
            app.state.authenticator = Authenticator(
                UserRepository(engine),
                settings.jwt_secret.get_secret_value(),
                settings.jwt_ttl_seconds,
            )
            registry = AgentRegistry(model_factory, checkpointer, store)
            for agent in agents:
                registry.register(agent)
            await registry.load_all()
            app.state.model_factory = model_factory
            app.state.registry = registry
            artifact_service = ArtifactService(
                ArtifactRepository(engine), artifact_store, settings.artifact_max_bytes
            )
            thread_repository = ThreadRepository(checkpointer, titles, cleanups=[artifact_service])
            project_service = ProjectService(
                ProjectRepository(engine),
                thread_repository,
                registry,
                model_factory,
                skill_registry,
            )
            await project_service.seed_builtin(builtin_projects)
            app.state.thread_repository = thread_repository
            app.state.memory_repository = UserMemoryRepository(store)
            app.state.trace_repository = RunTraceRepository(engine)
            app.state.project_service = project_service
            app.state.artifact_service = artifact_service
            yield
        logger.info("Service shut down")

    return lifespan
