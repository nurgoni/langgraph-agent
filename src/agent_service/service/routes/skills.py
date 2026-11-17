"""Endpoint `/skills` (read-only): skill yang bisa diaktifkan di project (FR-38, ADR 0005).

Endpoint tulis untuk skill buatan user ditambahkan di backlog B1.
"""

from fastapi import APIRouter

from agent_service.harness.skills.model import Skill
from agent_service.schema.skills import SkillDetail, SkillList, SkillSummary
from agent_service.service.dependencies import SkillRegistryDep

router = APIRouter(prefix="/skills", tags=["skills"])


def skill_summary(skill: Skill) -> SkillSummary:
    """Ubah skill harness menjadi schema API tanpa isi lengkap."""
    return SkillSummary(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        scope=skill.scope,
        version=skill.version,
        read_only=skill.read_only,
        resources=list(skill.resources),
    )


@router.get("")
async def list_skills(skills: SkillRegistryDep) -> SkillList:
    """Semua skill yang tersedia, urut ID."""
    return SkillList(skills=[skill_summary(skill) for skill in skills.list_skills()])


@router.get("/{skill_id:path}")
async def get_skill(skill_id: str, skills: SkillRegistryDep) -> SkillDetail:
    """Satu skill beserta isinya. ID berbentuk `<scope>/<name>`. Skill tidak dikenal → 404."""
    skill = skills.get(skill_id)
    return SkillDetail(**skill_summary(skill).model_dump(), body=skill.body)
