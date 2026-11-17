"""Model request dan response Project (FR-36, ADR 0004): agent deklaratif milik user.

>>> ProjectCreate(name="  Riset pasar ", base_agent_id="research-assistant").name
'Riset pasar'
>>> ProjectSettings().max_tokens is None
True
"""

from datetime import datetime
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

PROJECT_NAME_MAX_LENGTH: Final = 80
PROJECT_DESCRIPTION_MAX_LENGTH: Final = 500
PROJECT_INSTRUCTIONS_MAX_LENGTH: Final = 8000
MAX_PROJECT_SKILLS: Final = 20
# ID skill `<scope>/<name>` (ADR 0005). Nama mengikuti agentskills.io: huruf kecil, angka, tanda
# hubung tunggal, maksimal 64 karakter.
SKILL_ID_PATTERN: Final = r"^(builtin|org|user|project)/[a-z0-9]+(-[a-z0-9]+)*$"
SKILL_ID_MAX_LENGTH: Final = 72

type ProjectScope = Literal["builtin", "user"]

ProjectName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=PROJECT_NAME_MAX_LENGTH),
]
SkillId = Annotated[
    str, StringConstraints(pattern=SKILL_ID_PATTERN, max_length=SKILL_ID_MAX_LENGTH)
]


class ProjectSettings(BaseModel):
    """Pengaturan run di dalam project. Field baru selalu opsional, supaya tidak breaking."""

    model_config = ConfigDict(extra="forbid")

    max_tokens: int | None = Field(
        default=None,
        ge=1,
        description="Answer token limit for runs in this project. Empty uses LLM_MAX_TOKENS.",
    )


class ProjectCreate(BaseModel):
    """Body `POST /projects`."""

    model_config = ConfigDict(extra="forbid")

    name: ProjectName
    description: str = Field(default="", max_length=PROJECT_DESCRIPTION_MAX_LENGTH)
    base_agent_id: str = Field(
        min_length=1,
        description="Code agent that runs the project's chats (see /info). Cannot be changed.",
        examples=["research-assistant"],
    )
    model: str | None = Field(
        default=None, description="Default model for the project. Empty uses the service default."
    )
    instructions: str = Field(
        default="",
        max_length=PROJECT_INSTRUCTIONS_MAX_LENGTH,
        description="Extra instructions added to the system prompt of every run.",
    )
    skill_ids: list[SkillId] = Field(
        default_factory=list,
        max_length=MAX_PROJECT_SKILLS,
        description="Active skills, as ids from GET /skills.",
        examples=[["builtin/research-report"]],
    )
    settings: ProjectSettings = Field(default_factory=ProjectSettings)


class ProjectUpdate(BaseModel):
    """Body `PATCH /projects/{project_id}`. Hanya field yang dikirim yang diubah.

    `model: null` menghapus model project. `base_agent_id` tidak bisa diubah, karena thread lama
    terikat pada agent yang menjalankannya.
    """

    model_config = ConfigDict(extra="forbid")

    name: ProjectName | None = None
    description: str | None = Field(default=None, max_length=PROJECT_DESCRIPTION_MAX_LENGTH)
    model: str | None = None
    instructions: str | None = Field(default=None, max_length=PROJECT_INSTRUCTIONS_MAX_LENGTH)
    skill_ids: list[SkillId] | None = Field(default=None, max_length=MAX_PROJECT_SKILLS)
    settings: ProjectSettings | None = None


class Project(BaseModel):
    """Project yang terlihat oleh user: miliknya sendiri atau built-in."""

    id: str
    name: str
    description: str
    scope: ProjectScope = Field(description="`builtin` projects are shared and read-only.")
    read_only: bool
    base_agent_id: str
    model: str | None
    instructions: str
    skill_ids: list[str]
    settings: ProjectSettings
    created_at: datetime
    updated_at: datetime


class ProjectList(BaseModel):
    """Isi `GET /projects`: project built-in lebih dulu, lalu milik user, terbaru diubah dulu."""

    projects: list[Project]
