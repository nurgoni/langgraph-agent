"""Aturan akses dan siklus hidup Project (FR-36, ADR 0004).

- Project built-in terlihat oleh semua user dan read-only: mengubah atau menghapusnya → 403.
- Project milik user lain diperlakukan sebagai tidak ada (404), supaya keberadaannya tidak bocor.
- Menghapus project juga menghapus semua thread di dalamnya (keputusan user).
"""

import logging
from collections.abc import Iterable
from typing import Any, Final

from agent_service.agents.catalog import BuiltinProject
from agent_service.agents.registry import AgentRegistry
from agent_service.llm.factory import ModelFactory
from agent_service.memory.projects import (
    BUILTIN_SCOPE,
    ProjectFields,
    ProjectRecord,
    ProjectRepository,
)
from agent_service.schema.projects import Project, ProjectCreate, ProjectSettings, ProjectUpdate
from agent_service.service.run_input import ProjectRunContext
from agent_service.service.threads import ThreadRepository

logger = logging.getLogger(__name__)

SETTINGS_FIELD: Final = "settings"


class ProjectNotFoundError(Exception):
    """Project tidak ada, atau milik user lain (HTTP 404).

    >>> str(ProjectNotFoundError("p1"))
    "Project 'p1' not found"
    """

    def __init__(self, project_id: str) -> None:
        """Inisialisasi error.

        Args:
            project_id: ID project yang diminta.
        """
        super().__init__(f"Project {project_id!r} not found")
        self.project_id = project_id


class ProjectReadOnlyError(Exception):
    """Project built-in tidak bisa diubah atau dihapus (HTTP 403)."""

    def __init__(self, project_id: str) -> None:
        """Inisialisasi error.

        Args:
            project_id: ID project built-in.
        """
        super().__init__(f"Project {project_id!r} is built-in and read-only")
        self.project_id = project_id


class InvalidProjectError(ValueError):
    """Isi project merujuk agent yang tidak ada atau tidak tersedia (HTTP 422)."""


def project_to_schema(record: ProjectRecord) -> Project:
    """Ubah baris project menjadi schema API."""
    return Project(
        id=record.project_id,
        name=record.name,
        description=record.description,
        scope=record.scope,
        read_only=record.scope == BUILTIN_SCOPE,
        base_agent_id=record.base_agent_id,
        model=record.model,
        instructions=record.instructions,
        skill_ids=list(record.skill_ids),
        settings=ProjectSettings.model_validate(record.settings),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def run_context(record: ProjectRecord) -> ProjectRunContext:
    """Bagian project yang diteruskan ke run lewat `configurable`."""
    return ProjectRunContext(
        project_id=record.project_id,
        instructions=record.instructions,
        skill_ids=record.skill_ids,
    )


def project_max_tokens(record: ProjectRecord) -> int | None:
    """Batas token project, atau `None` untuk memakai `LLM_MAX_TOKENS` (FR-30)."""
    return ProjectSettings.model_validate(record.settings).max_tokens


class ProjectService:
    """Operasi project untuk user yang sedang login. Dibuat sekali di lifespan."""

    def __init__(
        self,
        projects: ProjectRepository,
        threads: ThreadRepository,
        registry: AgentRegistry,
        model_factory: ModelFactory,
    ) -> None:
        """Inisialisasi service.

        Args:
            projects: Penyimpanan project.
            threads: Repository thread, untuk menghapus thread saat project dihapus.
            registry: Registry agent, untuk memvalidasi `base_agent_id`.
            model_factory: Factory model, untuk memvalidasi `model` terhadap allowlist.
        """
        self._projects = projects
        self._threads = threads
        self._registry = registry
        self._model_factory = model_factory

    async def seed_builtin(self, builtins: Iterable[BuiltinProject]) -> list[str]:
        """Upsert project built-in yang agent dasarnya terdaftar. Aman dijalankan berulang.

        Returns:
            ID project built-in yang di-seed.
        """
        registered = {agent.agent_id for agent in self._registry.list_agents()}
        seeded: list[str] = []
        for builtin in builtins:
            if builtin.base_agent_id not in registered:
                logger.info(
                    "Skipping built-in project %r: agent %r is not registered",
                    builtin.project_id,
                    builtin.base_agent_id,
                )
                continue
            await self._projects.upsert_builtin(builtin.project_id, _builtin_fields(builtin))
            seeded.append(builtin.project_id)
        return seeded

    async def list_visible(self, user_id: str) -> list[Project]:
        """Project built-in dan milik user."""
        return [project_to_schema(record) for record in await self._projects.list_visible(user_id)]

    async def get_visible(self, project_id: str, user_id: str) -> ProjectRecord:
        """Project yang boleh dilihat user: built-in atau miliknya.

        Raises:
            ProjectNotFoundError: Jika project tidak ada atau milik user lain.
        """
        record = await self._projects.get(project_id)
        if record is None:
            raise ProjectNotFoundError(project_id)
        if record.scope != BUILTIN_SCOPE and record.owner_id != user_id:
            raise ProjectNotFoundError(project_id)
        return record

    async def create(self, user_id: str, project_create: ProjectCreate) -> Project:
        """Buat project milik user setelah memvalidasi agent dan model.

        Raises:
            InvalidProjectError: Jika `base_agent_id` tidak terdaftar atau tidak tersedia.
            UnknownModelError: Jika `model` tidak ada di allowlist (422).
        """
        self._validate_agent(project_create.base_agent_id)
        self._validate_model(project_create.model)
        fields = ProjectFields(
            name=project_create.name,
            base_agent_id=project_create.base_agent_id,
            description=project_create.description,
            model=project_create.model,
            instructions=project_create.instructions,
            skill_ids=project_create.skill_ids,
            settings=project_create.settings.model_dump(mode="json"),
        )
        record = await self._projects.create(user_id, fields)
        logger.info("Created project %s for user %s", record.project_id, user_id)
        return project_to_schema(record)

    async def update(self, project_id: str, user_id: str, project_update: ProjectUpdate) -> Project:
        """Ubah field yang dikirim saja (PATCH).

        Raises:
            ProjectNotFoundError: Jika project tidak ada atau milik user lain.
            ProjectReadOnlyError: Jika project built-in.
            UnknownModelError: Jika `model` baru tidak ada di allowlist (422).
        """
        await self._get_owned(project_id, user_id)
        changes = _changes(project_update)
        if "model" in changes:
            self._validate_model(changes["model"])
        if not changes:
            return project_to_schema(await self._get_owned(project_id, user_id))
        record = await self._projects.update(project_id, changes)
        if record is None:
            raise ProjectNotFoundError(project_id)
        return project_to_schema(record)

    async def delete(self, project_id: str, user_id: str) -> None:
        """Hapus project beserta semua thread di dalamnya.

        Raises:
            ProjectNotFoundError: Jika project tidak ada atau milik user lain.
            ProjectReadOnlyError: Jika project built-in.
        """
        record = await self._get_owned(project_id, user_id)
        await self._threads.delete_project_threads(user_id, record.base_agent_id, project_id)
        await self._projects.delete(project_id)
        logger.info("Deleted project %s for user %s", project_id, user_id)

    async def _get_owned(self, project_id: str, user_id: str) -> ProjectRecord:
        """Project milik user yang boleh diubah.

        Raises:
            ProjectNotFoundError: Jika project tidak ada atau milik user lain.
            ProjectReadOnlyError: Jika project built-in.
        """
        record = await self.get_visible(project_id, user_id)
        if record.scope == BUILTIN_SCOPE:
            raise ProjectReadOnlyError(project_id)
        return record

    def _validate_agent(self, agent_id: str) -> None:
        """Pastikan agent dasar terdaftar dan berhasil dimuat.

        Raises:
            InvalidProjectError: Jika agent tidak terdaftar atau tidak tersedia.
        """
        if not self._registry.is_available(agent_id):
            raise InvalidProjectError(f"Agent {agent_id!r} is not available for projects")

    def _validate_model(self, model_name: str | None) -> None:
        """Pastikan model ada di allowlist. `None` berarti model default service.

        Raises:
            UnknownModelError: Jika model tidak ada di allowlist.
        """
        if model_name is not None:
            self._model_factory.resolve_name(model_name)


def _builtin_fields(builtin: BuiltinProject) -> ProjectFields:
    """Isi project dari definisi built-in di katalog."""
    return ProjectFields(
        name=builtin.name,
        base_agent_id=builtin.base_agent_id,
        description=builtin.description,
        instructions=builtin.instructions,
        skill_ids=builtin.skill_ids,
    )


def _changes(project_update: ProjectUpdate) -> dict[str, Any]:  # Any: nilai kolom
    """Field yang dikirim di body PATCH, dalam bentuk nilai kolom.

    `settings` dikirim sebagai objek lengkap dan menggantikan pengaturan lama. Field yang
    dikirim `null` (selain `model`) diabaikan, karena kolomnya wajib terisi.

    >>> _changes(ProjectUpdate(name="Baru", model=None))
    {'name': 'Baru', 'model': None}
    """
    changes: dict[str, Any] = {}  # Any: nilai kolom
    for name in ProjectUpdate.model_fields:
        if name not in project_update.model_fields_set:
            continue
        value = getattr(project_update, name)
        if value is None and name != "model":
            continue
        if name == SETTINGS_FIELD:
            value = value.model_dump(mode="json")
        changes[name] = value
    return changes
