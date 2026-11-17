"""`SkillToolkit`: indeks skill aktif untuk prompt dan tool `load_skill` untuk agent (FR-38).

Satu objek dipakai agent untuk dua hal: mengisi slot `skills` di `ContextBuilder`, dan memberi
tahu tool apa yang perlu di-bind pada giliran ini. Tool hanya di-bind saat project punya skill
aktif (keputusan user, F28), jadi di luar project model tidak melihat tool skill sama sekali.
"""

from typing import Final

from langchain_core.tools import BaseTool

from agent_service.harness.context import SKILLS_MAX_CHARS, SKILLS_SECTION, PromptSection, RunConfig
from agent_service.harness.skills.model import Skill
from agent_service.harness.skills.registry import SkillRegistry
from agent_service.harness.tools.load_skill import active_skill_ids, create_load_skill_tool

SKILLS_TITLE: Final = "Skills"
SKILLS_INTRO: Final = (
    "Skills are step-by-step instructions for specific tasks. When a request matches a skill's "
    "description, call load_skill with its name before answering, then follow it. Do not load "
    "skills that are not relevant."
)


class SkillToolkit:
    """Indeks skill aktif dan tool `load_skill`, terikat pada satu `SkillRegistry`."""

    def __init__(self, registry: SkillRegistry) -> None:
        """Inisialisasi toolkit.

        Args:
            registry: Registry skill yang dimuat di lifespan.
        """
        self._registry = registry
        self._load_skill = create_load_skill_tool(registry)

    @property
    def tools(self) -> list[BaseTool]:
        """Semua tool yang mungkin dipakai, untuk didaftarkan di `ToolNode` saat compile."""
        return [self._load_skill]

    def active_skills(self, config: RunConfig | None) -> list[Skill]:
        """Skill aktif di project run ini yang dikenal registry."""
        return self._registry.active(active_skill_ids(config))

    def tools_for(self, config: RunConfig | None) -> list[BaseTool]:
        """Tool yang di-bind ke model pada giliran ini: `load_skill` jika ada skill aktif."""
        return self.tools if self.active_skills(config) else []

    def section(self, config: RunConfig) -> PromptSection | None:
        """Bagian `## Skills` berisi nama dan deskripsi skill aktif, atau `None` jika tidak ada."""
        skills = self.active_skills(config)
        if not skills:
            return None
        lines = [SKILLS_INTRO, ""]
        for skill in skills:
            lines.append(f"- {skill.name}: {skill.description}")
        return PromptSection(SKILLS_SECTION, "\n".join(lines), SKILLS_MAX_CHARS, SKILLS_TITLE)
