"""`SkillRegistry`: gabungan semua sumber skill, dimuat sekali saat startup (ADR 0005).

>>> import asyncio
>>> from agent_service.harness.skills.sources import BUILTIN_SKILLS_DIR, FilesystemSkillSource
>>> registry = SkillRegistry([FilesystemSkillSource(BUILTIN_SKILLS_DIR)])
>>> asyncio.run(registry.load())
>>> registry.get("builtin/meeting-notes").name
'meeting-notes'
"""

import logging
from collections.abc import Iterable, Sequence

from agent_service.harness.skills.model import Skill
from agent_service.harness.skills.sources import SkillSource

logger = logging.getLogger(__name__)


class SkillNotFoundError(LookupError):
    """Skill dengan ID ini tidak ada di registry (HTTP 404).

    >>> str(SkillNotFoundError("builtin/x"))
    "Skill 'builtin/x' not found"
    """

    def __init__(self, skill_id: str) -> None:
        """Inisialisasi error.

        Args:
            skill_id: ID skill yang diminta.
        """
        super().__init__(f"Skill {skill_id!r} not found")
        self.skill_id = skill_id


class SkillRegistry:
    """Skill dari semua sumber, per ID. Dibuat di `create_app`, dimuat di lifespan.

    Registry dibuat sebelum agent (agent memegang referensinya untuk tool `load_skill`), tetapi
    file baru dibaca saat `load()` dipanggil di lifespan.
    """

    def __init__(self, sources: Sequence[SkillSource]) -> None:
        """Inisialisasi registry kosong.

        Args:
            sources: Sumber skill. Sumber pertama menang jika ada ID yang sama.
        """
        self._sources = list(sources)
        self._skills: dict[str, Skill] = {}
        self._source_of: dict[str, SkillSource] = {}

    async def load(self) -> None:
        """Muat ulang semua skill dari semua sumber."""
        skills: dict[str, Skill] = {}
        source_of: dict[str, SkillSource] = {}
        for source in self._sources:
            for skill in await source.load():
                if skill.id in skills:
                    logger.warning("Skipping duplicate skill id %s", skill.id)
                    continue
                skills[skill.id] = skill
                source_of[skill.id] = source
        self._skills = skills
        self._source_of = source_of
        logger.info("Loaded %d skills: %s", len(skills), sorted(skills))

    def list_skills(self) -> list[Skill]:
        """Semua skill, urut ID."""
        return [self._skills[skill_id] for skill_id in sorted(self._skills)]

    def get(self, skill_id: str) -> Skill:
        """Skill dengan ID ini.

        Raises:
            SkillNotFoundError: Jika ID tidak dikenal.
        """
        skill = self._skills.get(skill_id)
        if skill is None:
            raise SkillNotFoundError(skill_id)
        return skill

    def contains(self, skill_id: str) -> bool:
        """Apakah ID ini dikenal registry."""
        return skill_id in self._skills

    def active(self, skill_ids: Iterable[str]) -> list[Skill]:
        """Skill yang dikenal dari `skill_ids`, urut sesuai `skill_ids`. ID asing dilewati."""
        skills: list[Skill] = []
        for skill_id in skill_ids:
            skill = self._skills.get(skill_id)
            if skill is not None and skill not in skills:
                skills.append(skill)
        return skills

    async def read_resource(self, skill: Skill, path: str) -> str:
        """Isi satu file pendukung skill dari sumbernya.

        Raises:
            SkillNotFoundError: Jika skill tidak berasal dari registry ini.
            SkillResourceNotFoundError: Jika `path` bukan resource skill ini.
        """
        source = self._source_of.get(skill.id)
        if source is None:
            raise SkillNotFoundError(skill.id)
        return await source.read_resource(skill, path)
