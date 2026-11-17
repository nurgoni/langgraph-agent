import logging
from pathlib import Path

import pytest

from agent_service.harness.skills.model import Skill, SkillScope
from agent_service.harness.skills.registry import SkillNotFoundError, SkillRegistry
from agent_service.harness.skills.sources import (
    BUILTIN_SKILLS_DIR,
    FilesystemSkillSource,
    SkillResourceNotFoundError,
)

VALID = "---\nname: {name}\ndescription: {description}\n---\nBody of {name}.\n"


def write_skill(root: Path, name: str, text: str | None = None, **resources: str) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    content = VALID.format(name=name, description=f"Use for {name}.") if text is None else text
    (folder / "SKILL.md").write_text(content, encoding="utf-8")
    for relative, resource_text in resources.items():
        resource = folder / relative.replace("__", "/")
        resource.parent.mkdir(parents=True, exist_ok=True)
        resource.write_text(resource_text, encoding="utf-8")


async def load(root: Path, scope: SkillScope = "builtin") -> SkillRegistry:
    registry = SkillRegistry([FilesystemSkillSource(root, scope=scope)])
    await registry.load()
    return registry


async def test_builtin_skills_are_all_valid(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        registry = await load(BUILTIN_SKILLS_DIR)

    assert [skill.id for skill in registry.list_skills()] == [
        "builtin/meeting-notes",
        "builtin/research-report",
    ]
    assert caplog.records == []
    report = registry.get("builtin/research-report")
    assert report.resources == ("references/report-template.md",)
    assert (report.scope, report.read_only, report.version) == ("builtin", True, "1")


async def test_invalid_skill_is_skipped_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_skill(tmp_path, "good")
    write_skill(tmp_path, "broken", text="no frontmatter here")
    (tmp_path / "not-a-skill").mkdir()

    with caplog.at_level(logging.WARNING):
        registry = await load(tmp_path)

    assert [skill.id for skill in registry.list_skills()] == ["builtin/good"]
    assert "Skipping invalid skill" in caplog.text
    assert "broken" in caplog.text


async def test_missing_folder_gives_empty_registry(tmp_path: Path) -> None:
    registry = await load(tmp_path / "missing")

    assert registry.list_skills() == []


async def test_resources_are_listed_without_skill_file_or_caches(tmp_path: Path) -> None:
    write_skill(
        tmp_path,
        "notes",
        references__template="T",
        assets__logo="L",
        __pycache__x="cache",
    )
    (tmp_path / "notes" / "__pycache__").mkdir(exist_ok=True)
    (tmp_path / "notes" / "__pycache__" / "x.pyc").write_text("c", encoding="utf-8")

    skill = (await load(tmp_path)).get("builtin/notes")

    assert skill.resources == ("assets/logo", "references/template")


async def test_read_resource_only_allows_listed_files(tmp_path: Path) -> None:
    write_skill(tmp_path, "notes", references__template="Isi template")
    (tmp_path / "secret.txt").write_text("rahasia", encoding="utf-8")
    registry = await load(tmp_path)
    skill = registry.get("builtin/notes")

    assert await registry.read_resource(skill, "references/template") == "Isi template"
    with pytest.raises(SkillResourceNotFoundError):
        await registry.read_resource(skill, "../secret.txt")


async def test_unknown_skill_id_is_not_found(tmp_path: Path) -> None:
    registry = await load(tmp_path)

    with pytest.raises(SkillNotFoundError, match="builtin/ghost"):
        registry.get("builtin/ghost")
    assert registry.contains("builtin/ghost") is False


async def test_active_keeps_order_and_drops_unknown_and_duplicates(tmp_path: Path) -> None:
    for name in ("alpha", "beta"):
        write_skill(tmp_path, name)
    registry = await load(tmp_path)

    active = registry.active(["builtin/beta", "builtin/ghost", "builtin/alpha", "builtin/beta"])

    assert [skill.name for skill in active] == ["beta", "alpha"]


async def test_first_source_wins_on_duplicate_ids(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    write_skill(first, "notes", text=VALID.format(name="notes", description="First."))
    write_skill(second, "notes", text=VALID.format(name="notes", description="Second."))
    registry = SkillRegistry([FilesystemSkillSource(first), FilesystemSkillSource(second)])

    with caplog.at_level(logging.WARNING):
        await registry.load()

    assert registry.get("builtin/notes").description == "First."
    assert "duplicate skill id builtin/notes" in caplog.text


async def test_resource_of_foreign_skill_is_rejected(tmp_path: Path) -> None:
    registry = await load(tmp_path)
    foreign = Skill("builtin/x", "x", "d", "b", "builtin", "1", True, ("a.md",))

    with pytest.raises(SkillNotFoundError):
        await registry.read_resource(foreign, "a.md")
