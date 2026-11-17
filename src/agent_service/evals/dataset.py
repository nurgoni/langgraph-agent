"""Format dataset eval (YAML di folder `evals/`).

Contoh::

    name: skills
    agent: chatbot
    project: general-assistant
    cases:
      - id: meeting-notes
        input: "Notes from standup: Budi will fix login by Friday."
        expect:
          skills_loaded: [meeting-notes]
          contains: ["Action items"]
          max_latency_seconds: 120

Agent dan project bisa diisi per dataset dan diganti per kasus. Setiap kasus berjalan di thread
baru, jadi kasus tidak saling memengaruhi.
"""

from pathlib import Path
from typing import Annotated, Final, Self

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

CASE_ID_PATTERN: Final = r"^[a-z0-9]+(-[a-z0-9]+)*$"

CaseId = Annotated[str, StringConstraints(pattern=CASE_ID_PATTERN, max_length=64)]


class DatasetError(ValueError):
    """File dataset tidak bisa dibaca, bukan YAML yang valid, atau tidak sesuai format."""


class Expectations(BaseModel):
    """Cek deterministik satu kasus. Semua cek yang diisi harus lolos."""

    model_config = ConfigDict(extra="forbid")

    contains: list[str] = Field(
        default_factory=list, description="Teks jawaban (tanpa beda huruf)."
    )
    not_contains: list[str] = Field(default_factory=list)
    tools_called: list[str] = Field(default_factory=list)
    tools_not_called: list[str] = Field(default_factory=list)
    skills_loaded: list[str] = Field(default_factory=list, description="Nama skill di load_skill.")
    max_latency_seconds: float | None = Field(default=None, gt=0)


class EvalCase(BaseModel):
    """Satu pesan ke agent beserta harapannya."""

    model_config = ConfigDict(extra="forbid")

    id: CaseId
    input: str = Field(min_length=1)
    agent: str | None = None
    project: str | None = None
    expect: Expectations = Field(default_factory=Expectations)


class EvalDataset(BaseModel):
    """Sekumpulan kasus dengan agent/project default.

    >>> dataset = EvalDataset(name="demo", agent="chatbot",
    ...                       cases=[EvalCase(id="hi", input="Halo", project="p1")])
    >>> dataset.target_for(dataset.cases[0])
    ('chatbot', 'p1')
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = ""
    agent: str | None = None
    project: str | None = None
    cases: list[EvalCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_case_ids(self) -> Self:
        """ID kasus harus unik di satu dataset, karena dipakai di laporan."""
        seen: set[str] = set()
        for case in self.cases:
            if case.id in seen:
                raise ValueError(f"Duplicate case id {case.id!r}")
            seen.add(case.id)
        return self

    def target_for(self, case: EvalCase) -> tuple[str | None, str | None]:
        """Agent dan project untuk kasus: nilai kasus, lalu nilai dataset."""
        return case.agent or self.agent, case.project or self.project


def load_dataset(path: Path) -> EvalDataset:
    """Baca dan validasi satu file dataset.

    Raises:
        DatasetError: Jika file tidak bisa dibaca, YAML rusak, atau format tidak valid.
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise DatasetError(f"Cannot read dataset {path}: {error}") from error
    try:
        return EvalDataset.model_validate(raw)
    except ValidationError as error:
        raise DatasetError(f"Invalid dataset {path}: {error}") from error
