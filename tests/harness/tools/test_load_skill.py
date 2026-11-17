from datetime import UTC, datetime

import pytest
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import ToolException

from agent_service.harness.context import ContextBuilder
from agent_service.harness.skills.registry import SkillRegistry
from agent_service.harness.skills.sources import BUILTIN_SKILLS_DIR, FilesystemSkillSource
from agent_service.harness.skills.toolkit import SkillToolkit
from agent_service.harness.tools.load_skill import (
    MAX_SKILL_CHARS,
    NO_ACTIVE_SKILLS_TEXT,
    create_load_skill_tool,
)

REPORT = "builtin/research-report"
NOTES = "builtin/meeting-notes"


def project_config(*skill_ids: str) -> RunnableConfig:
    return RunnableConfig(configurable={"project_skill_ids": list(skill_ids)})


@pytest.fixture
async def registry() -> SkillRegistry:
    skills = SkillRegistry([FilesystemSkillSource(BUILTIN_SKILLS_DIR)])
    await skills.load()
    return skills


async def test_active_skill_body_and_resources_are_returned(registry: SkillRegistry) -> None:
    tool = create_load_skill_tool(registry)

    content = await tool.ainvoke({"name": "research-report"}, config=project_config(REPORT))

    assert content.startswith("# Research report")
    assert content.endswith("Resources (load with path):\n- references/report-template.md")


@pytest.mark.parametrize(
    "path", ["references/report-template.md", "./references\\report-template.md"]
)
async def test_resource_is_loaded_by_path(registry: SkillRegistry, path: str) -> None:
    tool = create_load_skill_tool(registry)

    content = await tool.ainvoke(
        {"name": "research-report", "path": path}, config=project_config(REPORT)
    )

    assert content.startswith("# Report template")


async def test_inactive_skill_is_an_error_not_content(registry: SkillRegistry) -> None:
    tool = create_load_skill_tool(registry)

    with pytest.raises(ToolException, match="not available in this project") as error_info:
        await tool.ainvoke({"name": "research-report"}, config=project_config(NOTES))

    assert "meeting-notes" in str(error_info.value)
    assert "Research report" not in str(error_info.value)


async def test_without_project_skills_nothing_can_be_loaded(registry: SkillRegistry) -> None:
    tool = create_load_skill_tool(registry)

    with pytest.raises(ToolException, match=NO_ACTIVE_SKILLS_TEXT):
        await tool.ainvoke({"name": "meeting-notes"}, config=RunnableConfig(configurable={}))


@pytest.mark.parametrize("path", ["../meeting-notes/SKILL.md", "/etc/passwd", "SKILL.md", "x.md"])
async def test_paths_outside_the_skill_resources_are_rejected(
    registry: SkillRegistry, path: str
) -> None:
    tool = create_load_skill_tool(registry)

    with pytest.raises(ToolException):
        await tool.ainvoke({"name": "research-report", "path": path}, config=project_config(REPORT))


def test_tool_schema_hides_config() -> None:
    tool = create_load_skill_tool(SkillRegistry([]))

    assert sorted(tool.args) == ["name", "path"]


async def test_long_skill_is_truncated(
    registry: SkillRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("agent_service.harness.tools.load_skill.MAX_SKILL_CHARS", 20)
    tool = create_load_skill_tool(registry)

    content = await tool.ainvoke({"name": "meeting-notes"}, config=project_config(NOTES))

    assert content.endswith("[truncated]")
    assert MAX_SKILL_CHARS == 20_000


# ---------------- SkillToolkit


async def test_toolkit_binds_load_skill_only_with_active_skills(registry: SkillRegistry) -> None:
    toolkit = SkillToolkit(registry)

    assert toolkit.tools_for(project_config(NOTES)) == toolkit.tools
    assert toolkit.tools_for(project_config("builtin/ghost")) == []
    assert toolkit.tools_for({}) == []


async def test_skill_index_section_lists_active_skills_in_project_order(
    registry: SkillRegistry,
) -> None:
    toolkit = SkillToolkit(registry)
    builder = ContextBuilder(
        "Agent.", clock=lambda: datetime(2026, 11, 16, tzinfo=UTC), skills=toolkit
    )

    prompt = builder.build(project_config(REPORT, NOTES))

    skills_part = prompt.split("## Skills\n")[1].split("\n\n## Environment")[0]
    lines = skills_part.splitlines()
    assert "call load_skill with its name" in lines[0]
    assert lines[2].startswith("- research-report: Structure for a short research report")
    assert lines[3].startswith("- meeting-notes: Turns a meeting transcript")


async def test_no_skill_section_without_active_skills(registry: SkillRegistry) -> None:
    builder = ContextBuilder("Agent.", skills=SkillToolkit(registry))

    assert "## Skills" not in builder.build({"configurable": {}})
