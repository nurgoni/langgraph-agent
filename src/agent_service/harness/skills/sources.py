"""Sumber skill (ADR 0005). F28 hanya punya sumber filesystem untuk skill built-in.

Sumber lain (database, backlog B1) cukup memenuhi protokol `SkillSource`.
"""

import asyncio
import logging
from pathlib import Path, PurePosixPath
from typing import Final, Protocol

from agent_service.harness.skills.model import Skill, SkillScope, skill_id
from agent_service.harness.skills.parser import (
    InvalidSkillError,
    parse_skill_markdown,
    unknown_fields,
)

logger = logging.getLogger(__name__)

SKILL_FILENAME: Final = "SKILL.md"
ENCODING: Final = "utf-8"
# harness/skills/sources.py → parents[2] adalah folder package `agent_service`.
PACKAGE_ROOT: Final = Path(__file__).resolve().parents[2]
BUILTIN_SKILLS_DIR: Final = PACKAGE_ROOT / "skills" / "builtin"
MAX_RESOURCES_PER_SKILL: Final = 50
# Folder dan file yang bukan bagian skill (cache Python, file sistem operasi).
IGNORED_NAMES: Final = frozenset({"__pycache__", ".DS_Store"})


class SkillResourceNotFoundError(LookupError):
    """File pendukung tidak ada di daftar resource skill."""


class SkillSource(Protocol):
    """Asal skill. Setiap sumber memvalidasi skill-nya sendiri dan melewati yang tidak valid."""

    async def load(self) -> list[Skill]:
        """Semua skill valid dari sumber ini."""
        ...

    async def read_resource(self, skill: Skill, path: str) -> str:
        """Isi satu file pendukung skill.

        Raises:
            SkillResourceNotFoundError: Jika `path` bukan resource skill ini.
        """
        ...


class FilesystemSkillSource:
    """Skill dari folder `<root>/<name>/SKILL.md`, read-only dan ikut versi git.

    >>> import asyncio
    >>> skills = asyncio.run(FilesystemSkillSource(BUILTIN_SKILLS_DIR).load())
    >>> [skill.id for skill in skills]
    ['builtin/meeting-notes', 'builtin/research-report']
    """

    def __init__(self, root: Path, scope: SkillScope = "builtin") -> None:
        """Inisialisasi sumber tanpa membaca file.

        Args:
            root: Folder berisi satu subfolder per skill.
            scope: Scope semua skill di folder ini.
        """
        self._root = root
        self._scope = scope

    async def load(self) -> list[Skill]:
        """Baca dan validasi semua skill. Skill tidak valid dicatat di log lalu dilewati."""
        return await asyncio.to_thread(self._load_sync)

    async def read_resource(self, skill: Skill, path: str) -> str:
        """Isi satu file pendukung, hanya jika ada di `skill.resources`.

        Raises:
            SkillResourceNotFoundError: Jika `path` bukan resource skill ini.
        """
        if path not in skill.resources:
            raise SkillResourceNotFoundError(f"Skill {skill.name!r} has no resource {path!r}")
        file = self._root / skill.name / PurePosixPath(path)
        return await asyncio.to_thread(file.read_text, encoding=ENCODING)

    def _load_sync(self) -> list[Skill]:
        """Versi sinkron `load`, dijalankan di thread terpisah."""
        if not self._root.is_dir():
            logger.warning("Skill folder %s does not exist", self._root)
            return []
        skills: list[Skill] = []
        for folder in sorted(self._root.iterdir()):
            if folder.name in IGNORED_NAMES or not (folder / SKILL_FILENAME).is_file():
                continue
            skill = self._load_skill(folder)
            if skill is not None:
                skills.append(skill)
        return skills

    def _load_skill(self, folder: Path) -> Skill | None:
        """Satu skill dari foldernya, atau `None` jika tidak valid."""
        text = (folder / SKILL_FILENAME).read_text(encoding=ENCODING)
        try:
            parsed = parse_skill_markdown(text, folder_name=folder.name)
        except InvalidSkillError as error:
            logger.warning("Skipping invalid skill in %s: %s", folder, error)
            return None
        extra = unknown_fields(text)
        if extra:
            logger.info("Skill %s has frontmatter fields outside the spec: %s", folder.name, extra)
        return Skill(
            id=skill_id(self._scope, parsed.name),
            name=parsed.name,
            description=parsed.description,
            body=parsed.body,
            scope=self._scope,
            version=parsed.version,
            read_only=True,
            resources=_resources(folder),
        )


def _resources(folder: Path) -> tuple[str, ...]:
    """Path relatif (POSIX) semua file pendukung di folder skill, selain `SKILL.md`."""
    resources: list[str] = []
    for file in sorted(folder.rglob("*")):
        relative = file.relative_to(folder)
        if not file.is_file() or relative.as_posix() == SKILL_FILENAME:
            continue
        if IGNORED_NAMES.intersection(relative.parts):
            continue
        resources.append(relative.as_posix())
    if len(resources) > MAX_RESOURCES_PER_SKILL:
        logger.warning("Skill %s has more than %d resources", folder.name, MAX_RESOURCES_PER_SKILL)
    return tuple(resources[:MAX_RESOURCES_PER_SKILL])
