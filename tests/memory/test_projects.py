from collections.abc import AsyncIterator

import psycopg
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_service.memory.database import DatabaseEngineProvider
from agent_service.memory.projects import (
    ProjectFields,
    ProjectRepository,
    UnknownProjectColumnError,
)

OWNER = "user-a"
OTHER = "user-b"
CHAT_FIELDS = ProjectFields(name="Catatan", base_agent_id="chatbot")


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    async with DatabaseEngineProvider(database_url) as database_engine:
        yield database_engine


@pytest.fixture
def projects(engine: AsyncEngine) -> ProjectRepository:
    return ProjectRepository(engine)


async def test_created_project_round_trips(projects: ProjectRepository) -> None:
    fields = ProjectFields(
        name="Riset",
        base_agent_id="research-assistant",
        description="Riset pasar",
        model="fake",
        instructions="Selalu sebut sumber.",
        skill_ids=["research-report"],
        settings={"max_tokens": 512},
    )

    created = await projects.create(OWNER, fields)
    found = await projects.get(created.project_id)

    assert found == created
    assert (created.owner_id, created.scope) == (OWNER, "user")
    assert created.skill_ids == ("research-report",)
    assert created.settings == {"max_tokens": 512}


async def test_unknown_project_is_none(projects: ProjectRepository) -> None:
    assert await projects.get("missing") is None


async def test_builtin_upsert_is_idempotent_and_updates_content(
    projects: ProjectRepository,
) -> None:
    first = await projects.upsert_builtin("research-assistant", CHAT_FIELDS)
    second = await projects.upsert_builtin(
        "research-assistant", ProjectFields(name="Riset baru", base_agent_id="chatbot")
    )

    assert (second.project_id, second.scope, second.owner_id) == (
        "research-assistant",
        "builtin",
        None,
    )
    assert second.name == "Riset baru"
    assert second.created_at == first.created_at


async def test_list_shows_builtin_first_then_own_projects_only(
    projects: ProjectRepository,
) -> None:
    await projects.upsert_builtin("builtin-a", CHAT_FIELDS)
    older = await projects.create(OWNER, ProjectFields(name="Lama", base_agent_id="chatbot"))
    newer = await projects.create(OWNER, ProjectFields(name="Baru", base_agent_id="chatbot"))
    await projects.create(OTHER, ProjectFields(name="Milik B", base_agent_id="chatbot"))

    visible = await projects.list_visible(OWNER)

    assert [p.project_id for p in visible] == ["builtin-a", newer.project_id, older.project_id]


async def test_update_changes_given_columns_and_timestamp(projects: ProjectRepository) -> None:
    created = await projects.create(OWNER, CHAT_FIELDS)

    updated = await projects.update(
        created.project_id, {"name": "Diganti", "model": None, "skill_ids": ("meeting-notes",)}
    )

    assert updated is not None
    assert (updated.name, updated.model, updated.skill_ids) == ("Diganti", None, ("meeting-notes",))
    assert updated.base_agent_id == "chatbot"
    assert updated.updated_at >= created.updated_at


async def test_update_of_missing_project_is_none(projects: ProjectRepository) -> None:
    assert await projects.update("missing", {"name": "x"}) is None


@pytest.mark.parametrize("column", ["base_agent_id", "owner_id", "scope", "project_id"])
async def test_immutable_columns_cannot_be_updated(
    projects: ProjectRepository, column: str
) -> None:
    created = await projects.create(OWNER, CHAT_FIELDS)

    with pytest.raises(UnknownProjectColumnError):
        await projects.update(created.project_id, {column: "x"})


async def test_delete_removes_project(projects: ProjectRepository) -> None:
    created = await projects.create(OWNER, CHAT_FIELDS)

    assert await projects.delete(created.project_id) is True
    assert await projects.delete(created.project_id) is False
    assert await projects.get(created.project_id) is None


def test_database_rejects_builtin_with_owner(database_url: str) -> None:
    with (
        psycopg.connect(database_url, autocommit=True) as connection,
        pytest.raises(psycopg.errors.CheckViolation),
    ):
        connection.execute(
            "INSERT INTO projects (project_id, owner_id, scope, name, base_agent_id) "
            "VALUES ('x', 'user-a', 'builtin', 'X', 'chatbot')"
        )


async def test_builtin_projects_are_ordered_by_name_not_upsert_time(
    projects: ProjectRepository,
) -> None:
    await projects.upsert_builtin("b", ProjectFields(name="Beta", base_agent_id="chatbot"))
    await projects.upsert_builtin("a", ProjectFields(name="Alpha", base_agent_id="chatbot"))
    await projects.upsert_builtin("b", ProjectFields(name="Beta", base_agent_id="chatbot"))

    assert [p.name for p in await projects.list_visible(OWNER)] == ["Alpha", "Beta"]
