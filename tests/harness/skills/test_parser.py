import pytest

from agent_service.harness.skills.parser import (
    DESCRIPTION_MAX_LENGTH,
    InvalidSkillError,
    parse_skill_markdown,
    unknown_fields,
)


def skill_text(frontmatter: str, body: str = "# Steps\n1. Do it.") -> str:
    return f"---\n{frontmatter}\n---\n{body}\n"


def test_valid_skill_with_metadata_version() -> None:
    text = skill_text(
        'name: meeting-notes\ndescription: Summarize meetings.\nmetadata:\n  version: "2"'
    )

    skill = parse_skill_markdown(text, folder_name="meeting-notes")

    assert (skill.name, skill.description, skill.version) == (
        "meeting-notes",
        "Summarize meetings.",
        "2",
    )
    assert skill.body == "# Steps\n1. Do it."


def test_byte_order_mark_and_crlf_are_accepted() -> None:
    text = "﻿---\r\nname: a-b\r\ndescription: D\r\n---\r\nBody\r\n"

    assert parse_skill_markdown(text, folder_name="a-b").body == "Body"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("name: a\n", "must start with a '---'"),
        ("---\nname: a\ndescription: b\n", "not closed"),
        (skill_text("name: [a"), "not valid YAML"),
        (skill_text("- just\n- a list"), "YAML mapping"),
        (skill_text("description: no name"), "name is required"),
        (skill_text("name: Meeting_Notes\ndescription: d"), "lowercase letters"),
        (skill_text("name: meeting--notes\ndescription: d"), "lowercase letters"),
        (skill_text("name: -notes\ndescription: d"), "lowercase letters"),
        (skill_text("name: other-name\ndescription: d"), "must match its folder"),
        (skill_text("name: notes\ndescription: '   '"), "description is required"),
        (skill_text(f"name: notes\ndescription: {'x' * (DESCRIPTION_MAX_LENGTH + 1)}"), "at most"),
        (skill_text("name: notes\ndescription: d\ncompatibility: 42"), "compatibility"),
        (skill_text("name: notes\ndescription: d\nmetadata: [1, 2]"), "metadata"),
    ],
)
def test_invalid_skills_are_rejected_with_reason(text: str, message: str) -> None:
    folder = "other-folder" if "other-name" in text else "notes"
    folder = "meeting-notes" if "eeting" in text else folder

    with pytest.raises(InvalidSkillError, match=message):
        parse_skill_markdown(text, folder_name=folder)


def test_name_longer_than_64_characters_is_rejected() -> None:
    name = "a" * 65

    with pytest.raises(InvalidSkillError, match="at most 64"):
        parse_skill_markdown(skill_text(f"name: {name}\ndescription: d"), folder_name=name)


def test_unknown_fields_are_reported_but_allowed() -> None:
    text = skill_text("name: notes\ndescription: d\ntags: [x]\nlicense: MIT")

    assert parse_skill_markdown(text, folder_name="notes").name == "notes"
    assert unknown_fields(text) == ["tags"]
