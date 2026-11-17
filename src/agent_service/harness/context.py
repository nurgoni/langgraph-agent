"""Perakitan system prompt setiap giliran (FR-37, ADR 0002).

Urutan bagian tetap: instruksi agent → instruksi project → indeks skill → memory user (F30) →
ringkasan percakapan lama (F29) → lingkungan.
Setiap bagian punya batas ukuran sendiri, jadi satu sumber yang terlalu panjang (misalnya
instruksi project) tidak bisa menggeser bagian lain keluar dari prompt.

>>> from datetime import datetime, timezone
>>> monday = datetime(2026, 11, 16, tzinfo=timezone.utc)
>>> builder = ContextBuilder("You are helpful.", clock=lambda: monday)
>>> print(builder.build({"configurable": {"project_instructions": "Answer in Indonesian."}}))
You are helpful.
<BLANKLINE>
## Project instructions
Answer in Indonesian.
<BLANKLINE>
## Environment
Current date: Monday, November 16, 2026. Timezone: UTC (UTC+00:00).
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final, Protocol

from langchain_core.messages import SystemMessage

from agent_service.core.constants import PROJECT_INSTRUCTIONS_CONFIG_KEY

CONFIGURABLE_KEY: Final = "configurable"
SECTION_SEPARATOR: Final = "\n\n"
TRUNCATION_MARKER: Final = "\n[truncated]"

AGENT_SECTION: Final = "agent"
PROJECT_SECTION: Final = "project"
SKILLS_SECTION: Final = "skills"
MEMORY_SECTION: Final = "memory"
SUMMARY_SECTION: Final = "summary"
ENVIRONMENT_SECTION: Final = "environment"

# Batas karakter per bagian. Instruksi project sama dengan batas schema `ProjectCreate`.
AGENT_MAX_CHARS: Final = 8000
PROJECT_MAX_CHARS: Final = 8000
SKILLS_MAX_CHARS: Final = 4000
MEMORY_MAX_CHARS: Final = 4000
SUMMARY_MAX_CHARS: Final = 4000
ENVIRONMENT_MAX_CHARS: Final = 300

PROJECT_TITLE: Final = "Project instructions"
MEMORY_TITLE: Final = "Memory"
SUMMARY_TITLE: Final = "Summary of earlier conversation"
ENVIRONMENT_TITLE: Final = "Environment"
ENVIRONMENT_TEMPLATE: Final = "Current date: {date}. Timezone: {zone} (UTC{offset})."
DATE_FORMAT: Final = "%A, %B %d, %Y"
SECONDS_PER_MINUTE: Final = 60
MINUTES_PER_HOUR: Final = 60

type Clock = Callable[[], datetime]
# Any: RunnableConfig LangGraph berupa dict bebas (TypedDict dengan total=False).
type RunConfig = Mapping[str, Any]


def local_now() -> datetime:
    """Waktu lokal saat ini dengan timezone, dihitung setiap kali dipanggil (bukan saat import)."""
    return datetime.now().astimezone()


@dataclass(frozen=True)
class PromptSection:
    """Satu bagian system prompt beserta batas ukurannya.

    >>> PromptSection("project", "abcdef", max_chars=3, title="Project").render()
    '## Project\\nabc\\n[truncated]'
    """

    name: str
    text: str
    max_chars: int
    title: str | None = None

    def render(self) -> str:
        """Teks bagian, dipotong ke `max_chars` (di luar judul), dengan judul jika ada."""
        body = self.text.strip()
        if len(body) > self.max_chars:
            body = body[: self.max_chars].rstrip() + TRUNCATION_MARKER
        if self.title is None:
            return body
        return f"## {self.title}\n{body}"

    @property
    def is_empty(self) -> bool:
        """Bagian tanpa isi tidak ikut ke prompt."""
        return not self.text.strip()


class SectionProvider(Protocol):
    """Sumber satu bagian prompt yang bergantung pada run, misalnya indeks skill (F28)."""

    def section(self, config: RunConfig) -> PromptSection | None:
        """Bagian untuk run ini, atau `None` jika tidak ada yang ditambahkan."""
        ...


class ContextBuilder:
    """Merakit system prompt dari bagian-bagian berurutan, setiap kali model dipanggil.

    Dibuat sekali per agent dan dipakai ulang oleh semua graph-nya. Isi yang berubah per run
    (instruksi project, skill aktif, tanggal) dibaca dari `config` dan `clock` saat `build`.
    """

    def __init__(
        self,
        instructions: str = "",
        clock: Clock = local_now,
        use_project_instructions: bool = True,
        skills: SectionProvider | None = None,
    ) -> None:
        """Inisialisasi builder.

        Args:
            instructions: Instruksi agent dari kode (bagian pertama, tanpa judul).
            clock: Sumber waktu untuk bagian lingkungan, bisa diganti di test.
            use_project_instructions: `False` untuk sub-agent yang tidak berbicara langsung
                dengan user (misalnya expert supervisor), supaya instruksi project tidak
                mengubah tugas teknisnya.
            skills: Sumber indeks skill aktif (F28). `None` berarti tanpa bagian skill.

        Memory user (F30) dan ringkasan (F29) tidak punya provider: keduanya dibaca agent secara
        async (store, state thread) lalu diberikan ke `build` per panggilan.
        """
        self._instructions = instructions
        self._clock = clock
        self._use_project_instructions = use_project_instructions
        self._skills = skills

    def with_skills(self, skills: SectionProvider) -> "ContextBuilder":
        """Builder yang sama dengan sumber indeks skill, untuk agent yang punya `load_skill`.

        Agent memasangnya sendiri dari toolkit skill-nya, supaya indeks di prompt dan tool yang
        di-bind selalu berasal dari sumber yang sama.
        """
        return ContextBuilder(
            self._instructions,
            clock=self._clock,
            use_project_instructions=self._use_project_instructions,
            skills=skills,
        )

    def sections(
        self, config: RunConfig | None = None, summary: str = "", memories: str = ""
    ) -> list[PromptSection]:
        """Semua bagian yang berisi, urut sesuai FR-37.

        Args:
            config: Config run LangGraph. Instruksi project dibaca dari `configurable`.
            summary: Ringkasan giliran lama dari state thread (F29), kosong jika belum ada.
            memories: Memory user yang sudah dirender (F30), kosong jika tidak ada.
        """
        run_config: RunConfig = {} if config is None else config
        candidates = [
            PromptSection(AGENT_SECTION, self._instructions, AGENT_MAX_CHARS),
            self._project_section(run_config),
            _provided(self._skills, run_config),
            PromptSection(MEMORY_SECTION, memories, MEMORY_MAX_CHARS, MEMORY_TITLE),
            PromptSection(SUMMARY_SECTION, summary, SUMMARY_MAX_CHARS, SUMMARY_TITLE),
            self._environment_section(),
        ]
        return [section for section in candidates if section is not None and not section.is_empty]

    def build(self, config: RunConfig | None = None, summary: str = "", memories: str = "") -> str:
        """System prompt lengkap untuk run ini."""
        sections = self.sections(config, summary, memories)
        return SECTION_SEPARATOR.join(section.render() for section in sections)

    def system_message(
        self, config: RunConfig | None = None, summary: str = "", memories: str = ""
    ) -> SystemMessage:
        """System prompt sebagai message pertama untuk model. Tidak disimpan di riwayat thread.

        Args:
            config: Config run LangGraph.
            summary: Ringkasan giliran lama dari `ContextPolicy`, kosong jika belum ada.
            memories: Memory user dari `MemoryToolkit`, kosong jika tidak ada.
        """
        return SystemMessage(content=self.build(config, summary, memories))

    def _project_section(self, config: RunConfig) -> PromptSection | None:
        """Instruksi project dari `configurable`, jika run berada di project dan dipakai agent."""
        if not self._use_project_instructions:
            return None
        configurable = config.get(CONFIGURABLE_KEY) or {}
        instructions = configurable.get(PROJECT_INSTRUCTIONS_CONFIG_KEY)
        if not isinstance(instructions, str):
            return None
        return PromptSection(PROJECT_SECTION, instructions, PROJECT_MAX_CHARS, PROJECT_TITLE)

    def _environment_section(self) -> PromptSection:
        """Tanggal dan timezone saat model dipanggil."""
        now = self._clock()
        text = ENVIRONMENT_TEMPLATE.format(
            date=now.strftime(DATE_FORMAT),
            zone=now.tzname() or "local time",
            offset=format_utc_offset(now.utcoffset()),
        )
        return PromptSection(ENVIRONMENT_SECTION, text, ENVIRONMENT_MAX_CHARS, ENVIRONMENT_TITLE)


def format_utc_offset(offset: timedelta | None) -> str:
    """Offset UTC dalam bentuk `+07:00`. Waktu tanpa timezone dianggap UTC.

    >>> format_utc_offset(timedelta(hours=7))
    '+07:00'
    >>> format_utc_offset(timedelta(hours=-3, minutes=-30))
    '-03:30'
    """
    total_minutes = 0 if offset is None else int(offset.total_seconds()) // SECONDS_PER_MINUTE
    sign = "-" if total_minutes < 0 else "+"
    hours, minutes = divmod(abs(total_minutes), MINUTES_PER_HOUR)
    return f"{sign}{hours:02d}:{minutes:02d}"


def _provided(provider: SectionProvider | None, config: RunConfig) -> PromptSection | None:
    """Bagian dari provider opsional."""
    return None if provider is None else provider.section(config)
