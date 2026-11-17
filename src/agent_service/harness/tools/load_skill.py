"""Tool `load_skill(name, path?)`: progressive disclosure skill (FR-38, ADR 0005).

Model melihat indeks skill (nama + deskripsi) di system prompt, lalu memuat isi lengkap hanya saat
dibutuhkan. Tool hanya bisa memuat skill yang aktif di project run ini, yang dibaca dari
`configurable["project_skill_ids"]`.
"""

from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any, Final

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, ToolException, tool

from agent_service.core.constants import PROJECT_SKILL_IDS_CONFIG_KEY
from agent_service.harness.skills.model import Skill
from agent_service.harness.skills.registry import SkillRegistry
from agent_service.harness.skills.sources import SkillResourceNotFoundError

LOAD_SKILL_TOOL_NAME: Final = "load_skill"
CONFIGURABLE_KEY: Final = "configurable"
# Batas isi yang dikembalikan ke model, supaya satu file referensi tidak menghabiskan konteks.
MAX_SKILL_CHARS: Final = 20_000
TRUNCATION_NOTE: Final = "\n\n[truncated]"
RESOURCES_HEADING: Final = "Resources (load with path):"
NO_ACTIVE_SKILLS_TEXT: Final = "No skills are active in this project."


def active_skill_ids(config: Mapping[str, Any] | None) -> list[str]:  # Any: RunnableConfig
    """ID skill aktif dari `configurable`, atau daftar kosong di luar project.

    >>> active_skill_ids({"configurable": {"project_skill_ids": ["builtin/meeting-notes"]}})
    ['builtin/meeting-notes']
    >>> active_skill_ids({})
    []
    """
    configurable = (config or {}).get(CONFIGURABLE_KEY) or {}
    value = configurable.get(PROJECT_SKILL_IDS_CONFIG_KEY)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def render_skill(skill: Skill) -> str:
    """Isi lengkap skill untuk model, diikuti daftar file pendukungnya.

    >>> from agent_service.harness.skills.model import Skill
    >>> skill = Skill("builtin/a", "a", "d", "Do X.", "builtin", "1", True, ("ref.md",))
    >>> print(render_skill(skill))
    Do X.
    <BLANKLINE>
    Resources (load with path):
    - ref.md
    """
    text = skill.body
    if skill.resources:
        listing = "\n".join(f"- {resource}" for resource in skill.resources)
        text = f"{text}\n\n{RESOURCES_HEADING}\n{listing}"
    return _limit(text)


def create_load_skill_tool(registry: SkillRegistry) -> BaseTool:
    """Buat tool `load_skill` yang terikat pada `registry`.

    Function, bukan class: factory `@tool` (AGENTS.md § Class vs Function). Tool dibuat sekali
    per agent, dan skill aktif dibaca dari config setiap pemanggilan.
    """

    @tool(LOAD_SKILL_TOOL_NAME)
    async def load_skill(name: str, config: RunnableConfig, path: str | None = None) -> str:
        """Load the full instructions of a skill listed under "Skills" in your instructions.

        Call this before doing a task that matches a skill's description, then follow the
        skill. To read a file the skill refers to, call again with that file's path.

        Args:
            name: Skill name exactly as listed, for example "meeting-notes".
            path: Optional file inside the skill, for example "references/template.md".
        """
        skill = _find_active_skill(registry, name, active_skill_ids(config))
        if path is None:
            return render_skill(skill)
        try:
            content = await registry.read_resource(skill, _normalize_path(path))
        except SkillResourceNotFoundError as error:
            raise ToolException(f"{error}. Available: {list(skill.resources)}") from error
        return _limit(content)

    return load_skill


def _find_active_skill(registry: SkillRegistry, name: str, skill_ids: list[str]) -> Skill:
    """Skill aktif dengan nama ini.

    Raises:
        ToolException: Jika tidak ada skill aktif, atau nama tidak cocok dengan skill aktif.
    """
    active = registry.active(skill_ids)
    if not active:
        raise ToolException(NO_ACTIVE_SKILLS_TEXT)
    for skill in active:
        if skill.name == name:
            return skill
    names = [skill.name for skill in active]
    raise ToolException(f"Skill {name!r} is not available in this project. Available: {names}")


def _normalize_path(path: str) -> str:
    """Path relatif tanpa `..`, `.`, atau awalan `/`, dalam bentuk POSIX.

    >>> _normalize_path("./references\\\\report-template.md")
    'references/report-template.md'

    Raises:
        ToolException: Jika path absolut atau keluar dari folder skill.
    """
    candidate = PurePosixPath(path.strip().replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ToolException(f"Path {path!r} must stay inside the skill folder")
    return PurePosixPath(*[part for part in candidate.parts if part != "."]).as_posix()


def _limit(text: str) -> str:
    """Potong teks ke `MAX_SKILL_CHARS` dengan catatan."""
    if len(text) <= MAX_SKILL_CHARS:
        return text
    return text[:MAX_SKILL_CHARS] + TRUNCATION_NOTE
