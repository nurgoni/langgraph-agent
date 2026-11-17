import logging
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from agent_service.agents.chatbot import ChatbotAgent
from agent_service.core.settings import Settings
from agent_service.harness.skills.registry import SkillRegistry
from agent_service.harness.skills.sources import FilesystemSkillSource
from agent_service.memory.users import UserRecord
from agent_service.schema.skills import SkillDetail, SkillList
from agent_service.service.app import create_app


async def test_list_skills_returns_builtin_summaries(client: AsyncClient) -> None:
    listing = SkillList.model_validate((await client.get("/skills")).json())

    assert [skill.id for skill in listing.skills] == [
        "builtin/meeting-notes",
        "builtin/research-report",
    ]
    report = listing.skills[1]
    assert (report.name, report.scope, report.read_only) == ("research-report", "builtin", True)
    assert report.resources == ["references/report-template.md"]
    assert "body" not in (await client.get("/skills")).json()["skills"][0]


async def test_get_skill_includes_body(client: AsyncClient) -> None:
    response = await client.get("/skills/builtin/meeting-notes")

    skill = SkillDetail.model_validate(response.json())
    assert skill.body.startswith("# Meeting notes")


@pytest.mark.parametrize("path", ["/skills/builtin/ghost", "/skills/meeting-notes"])
async def test_unknown_skill_is_404(client: AsyncClient, path: str) -> None:
    response = await client.get(path)

    assert response.status_code == 404


async def test_skills_need_a_token(anonymous_client: AsyncClient) -> None:
    assert (await anonymous_client.get("/skills")).status_code == 401


async def test_project_rejects_unknown_skill(client: AsyncClient) -> None:
    response = await client.post(
        "/projects",
        json={"name": "X", "base_agent_id": "chatbot", "skill_ids": ["builtin/ghost"]},
    )

    assert response.status_code == 422
    assert "builtin/ghost" in response.json()["detail"]


async def test_project_skills_can_be_updated(client: AsyncClient) -> None:
    created = await client.post("/projects", json={"name": "X", "base_agent_id": "chatbot"})
    project_id = created.json()["id"]

    updated = await client.patch(
        f"/projects/{project_id}", json={"skill_ids": ["builtin/research-report"]}
    )
    rejected = await client.patch(f"/projects/{project_id}", json={"skill_ids": ["builtin/x"]})

    assert updated.json()["skill_ids"] == ["builtin/research-report"]
    assert rejected.status_code == 422


async def test_builtin_project_comes_with_its_skill(client: AsyncClient) -> None:
    project = (await client.get("/projects/general-assistant")).json()

    assert project["skill_ids"] == ["builtin/meeting-notes"]


@pytest.fixture
async def custom_skill_client(
    database_url: str, tmp_path: Path
) -> AsyncIterator[tuple[AsyncClient, FastAPI]]:
    good = tmp_path / "good"
    good.mkdir()
    (good / "SKILL.md").write_text("---\nname: good\ndescription: d\n---\nOK", encoding="utf-8")
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "SKILL.md").write_text("missing frontmatter", encoding="utf-8")
    registry = SkillRegistry([FilesystemSkillSource(tmp_path)])
    settings = Settings(_env_file=None, use_fake_model=True, database_url=database_url)
    app = create_app(settings, agents=[ChatbotAgent()], skill_registry=registry)
    async with app.router.lifespan_context(app):
        user = UserRecord(user_id="user-a", username="user-a", password_hash="", role="user")
        token = app.state.authenticator.issue_token(user).access_token
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            yield client, app


async def test_invalid_skill_does_not_stop_startup(
    custom_skill_client: tuple[AsyncClient, FastAPI], caplog: pytest.LogCaptureFixture
) -> None:
    client, _ = custom_skill_client

    listing = (await client.get("/skills")).json()

    assert [skill["id"] for skill in listing["skills"]] == ["builtin/good"]


async def test_builtin_project_skips_skills_that_are_not_loaded(
    custom_skill_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, _ = custom_skill_client

    project = (await client.get("/projects/general-assistant")).json()

    assert project["skill_ids"] == []


async def test_startup_logs_invalid_skill(
    database_url: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "SKILL.md").write_text("missing frontmatter", encoding="utf-8")
    settings = Settings(_env_file=None, use_fake_model=True, database_url=database_url)
    app = create_app(
        settings,
        agents=[ChatbotAgent()],
        skill_registry=SkillRegistry([FilesystemSkillSource(tmp_path)]),
    )

    with caplog.at_level(logging.WARNING):
        async with app.router.lifespan_context(app):
            assert app.state.skill_registry.list_skills() == []

    assert "Skipping invalid skill" in caplog.text
