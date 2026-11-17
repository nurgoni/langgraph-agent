"""Model response skill (FR-38, ADR 0005). Skill built-in hanya bisa dibaca.

>>> SkillSummary(id="builtin/a", name="a", description="d", scope="builtin", version="1",
...              read_only=True).resources
[]
"""

from typing import Literal

from pydantic import BaseModel, Field

type SkillScope = Literal["builtin", "org", "user", "project"]


class SkillSummary(BaseModel):
    """Skill tanpa isi lengkap, untuk daftar dan pemilih skill di project."""

    id: str = Field(examples=["builtin/research-report"])
    name: str = Field(description="Short name the model uses with load_skill.")
    description: str = Field(description="When the model should load this skill.")
    scope: SkillScope
    version: str
    read_only: bool
    resources: list[str] = Field(
        default_factory=list, description="Supporting files, relative to the skill folder."
    )


class SkillDetail(SkillSummary):
    """Skill lengkap dengan isi Markdown-nya."""

    body: str


class SkillList(BaseModel):
    """Isi `GET /skills`, urut ID."""

    skills: list[SkillSummary]
