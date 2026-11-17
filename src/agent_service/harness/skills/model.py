"""Model data skill yang sama untuk semua sumber (ADR 0005).

ID skill berbentuk `<scope>/<name>`, misalnya `builtin/research-report`. Model memakai nama
pendek (`research-report`) saat memanggil `load_skill`, karena nama unik di antara skill yang
aktif di satu project.

>>> skill_id("builtin", "research-report")
'builtin/research-report'
>>> split_skill_id("builtin/research-report")
('builtin', 'research-report')
"""

from dataclasses import dataclass
from typing import Final, Literal

type SkillScope = Literal["builtin", "org", "user", "project"]
SKILL_ID_SEPARATOR: Final = "/"


class InvalidSkillIdError(ValueError):
    """ID skill tidak berbentuk `<scope>/<name>`."""


@dataclass(frozen=True)
class Skill:
    """Satu skill yang sudah divalidasi.

    `resources` berisi path relatif (POSIX) file pendukung di folder skill, misalnya
    `references/template.md`. Isinya dibaca lewat `SkillRegistry.read_resource`.
    """

    id: str
    name: str
    description: str
    body: str
    scope: SkillScope
    version: str
    read_only: bool
    resources: tuple[str, ...] = ()
    owner_id: str | None = None


def skill_id(scope: SkillScope, name: str) -> str:
    """Gabungkan scope dan nama menjadi ID skill."""
    return f"{scope}{SKILL_ID_SEPARATOR}{name}"


def split_skill_id(value: str) -> tuple[str, str]:
    """Pisahkan ID skill menjadi `(scope, name)`.

    Raises:
        InvalidSkillIdError: Jika ID tidak berisi tepat satu pemisah `/`.
    """
    parts = value.split(SKILL_ID_SEPARATOR)
    if len(parts) != 2 or not all(parts):
        raise InvalidSkillIdError(f"Skill id must look like '<scope>/<name>', got {value!r}")
    return parts[0], parts[1]
