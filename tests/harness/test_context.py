from datetime import UTC, datetime, timedelta, timezone

import pytest
from langchain_core.messages import SystemMessage

from agent_service.harness.context import (
    AGENT_MAX_CHARS,
    ENVIRONMENT_SECTION,
    MEMORY_SECTION,
    PROJECT_MAX_CHARS,
    SKILLS_SECTION,
    SUMMARY_MAX_CHARS,
    SUMMARY_SECTION,
    TRUNCATION_MARKER,
    ContextBuilder,
    PromptSection,
    RunConfig,
    local_now,
)

JAKARTA = timezone(timedelta(hours=7), "WIB")
FIXED_NOW = datetime(2026, 11, 16, 9, 30, tzinfo=JAKARTA)
PROJECT_CONFIG = {"configurable": {"project_instructions": "Jawab dalam poin."}}


def fixed_clock() -> datetime:
    return FIXED_NOW


class StaticProvider:
    """Sumber bagian tiruan untuk slot skill/memory."""

    def __init__(self, section: PromptSection | None) -> None:
        self.section_value = section
        self.configs: list[RunConfig] = []

    def section(self, config: RunConfig) -> PromptSection | None:
        self.configs.append(config)
        return self.section_value


def test_full_prompt_snapshot() -> None:
    builder = ContextBuilder(
        "You are a research assistant.",
        clock=fixed_clock,
        skills=StaticProvider(PromptSection(SKILLS_SECTION, "- research-report", 100, "Skills")),
        memory=StaticProvider(
            PromptSection(MEMORY_SECTION, "- Prefers short answers", 100, "Memory")
        ),
    )

    prompt = builder.build(PROJECT_CONFIG, summary="User is planning a trip to Bali.")

    assert prompt == (
        "You are a research assistant.\n"
        "\n"
        "## Project instructions\n"
        "Jawab dalam poin.\n"
        "\n"
        "## Skills\n"
        "- research-report\n"
        "\n"
        "## Memory\n"
        "- Prefers short answers\n"
        "\n"
        "## Summary of earlier conversation\n"
        "User is planning a trip to Bali.\n"
        "\n"
        "## Environment\n"
        "Current date: Monday, November 16, 2026. Timezone: WIB (UTC+07:00)."
    )


def test_summary_section_is_bounded_and_skipped_when_empty() -> None:
    builder = ContextBuilder("Be concise.", clock=fixed_clock)

    long_summary = builder.sections(summary="s" * (SUMMARY_MAX_CHARS + 50))
    no_summary = builder.sections(summary="  ")

    [summary] = [section for section in long_summary if section.name == SUMMARY_SECTION]
    assert summary.render().endswith("s" + TRUNCATION_MARKER)
    assert SUMMARY_SECTION not in [section.name for section in no_summary]


def test_prompt_without_project_is_agent_instructions_plus_environment() -> None:
    prompt = ContextBuilder("Be concise.", clock=fixed_clock).build({"configurable": {}})

    assert prompt == (
        "Be concise.\n\n## Environment\n"
        "Current date: Monday, November 16, 2026. Timezone: WIB (UTC+07:00)."
    )


@pytest.mark.parametrize("config", [None, {}, {"configurable": None}])
def test_missing_config_is_treated_as_no_project(config: RunConfig | None) -> None:
    sections = ContextBuilder("Halo", clock=fixed_clock).sections(config)

    assert [section.name for section in sections] == ["agent", ENVIRONMENT_SECTION]


def test_empty_agent_instructions_leave_only_environment() -> None:
    sections = ContextBuilder(clock=fixed_clock).sections(PROJECT_CONFIG)

    assert [section.name for section in sections] == ["project", ENVIRONMENT_SECTION]


@pytest.mark.parametrize("instructions", ["", "   \n", 42])
def test_blank_or_invalid_project_instructions_are_skipped(instructions: object) -> None:
    config = {"configurable": {"project_instructions": instructions}}

    sections = ContextBuilder("Halo", clock=fixed_clock).sections(config)

    assert "project" not in [section.name for section in sections]


def test_sub_agents_can_ignore_project_instructions() -> None:
    builder = ContextBuilder("Solve the math.", clock=fixed_clock, use_project_instructions=False)

    assert "Jawab dalam poin." not in builder.build(PROJECT_CONFIG)


def test_each_section_is_truncated_to_its_own_limit() -> None:
    config = {"configurable": {"project_instructions": "p" * (PROJECT_MAX_CHARS + 50)}}
    builder = ContextBuilder("a" * (AGENT_MAX_CHARS + 50), clock=fixed_clock)

    agent, project, environment = [section.render() for section in builder.sections(config)]

    assert agent == "a" * AGENT_MAX_CHARS + TRUNCATION_MARKER
    assert project == "## Project instructions\n" + "p" * PROJECT_MAX_CHARS + TRUNCATION_MARKER
    assert environment.startswith("## Environment\nCurrent date:")


def test_long_project_instructions_do_not_push_out_environment() -> None:
    config = {"configurable": {"project_instructions": "x" * 100_000}}

    prompt = ContextBuilder("Halo", clock=fixed_clock).build(config)

    assert prompt.endswith("Timezone: WIB (UTC+07:00).")
    assert len(prompt) < AGENT_MAX_CHARS + PROJECT_MAX_CHARS + 1_000


def test_providers_receive_run_config_and_can_return_nothing() -> None:
    skills = StaticProvider(None)
    memory = StaticProvider(PromptSection(MEMORY_SECTION, "  ", 100, "Memory"))
    builder = ContextBuilder("Halo", clock=fixed_clock, skills=skills, memory=memory)

    sections = builder.sections(PROJECT_CONFIG)

    assert skills.configs == [PROJECT_CONFIG]
    assert [section.name for section in sections] == ["agent", "project", ENVIRONMENT_SECTION]


def test_clock_is_read_on_every_build() -> None:
    moments = iter([FIXED_NOW, FIXED_NOW + timedelta(days=1)])
    builder = ContextBuilder("Halo", clock=lambda: next(moments))

    first, second = builder.build(), builder.build()

    assert "November 16, 2026" in first
    assert "November 17, 2026" in second


def test_naive_clock_is_reported_as_utc_offset_zero() -> None:
    builder = ContextBuilder(clock=lambda: datetime(2026, 1, 1, 12, 0))

    assert builder.build().endswith("Timezone: local time (UTC+00:00).")


def test_system_message_wraps_prompt() -> None:
    message = ContextBuilder(
        "Halo", clock=lambda: datetime(2026, 1, 1, tzinfo=UTC)
    ).system_message()

    assert isinstance(message, SystemMessage)
    assert message.text.startswith("Halo\n\n## Environment")


def test_local_now_is_timezone_aware() -> None:
    assert local_now().tzinfo is not None
