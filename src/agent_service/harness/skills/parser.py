"""Parser dan validator `SKILL.md` sesuai spesifikasi Agent Skills (agentskills.io).

Isi file: frontmatter YAML di antara dua baris `---`, lalu isi Markdown. Field wajib `name` (1–64
karakter: huruf kecil, angka, tanda hubung tunggal, sama dengan nama folder) dan `description`
(1–1024 karakter). Field opsional: `license`, `compatibility` (≤ 500 karakter), `metadata`
(peta string ke string), dan `allowed-tools`.

>>> skill = parse_skill_markdown(
...     "---\\nname: meeting-notes\\ndescription: Summarize meetings.\\n---\\n# Steps\\n",
...     folder_name="meeting-notes",
... )
>>> skill.name, skill.description, skill.body
('meeting-notes', 'Summarize meetings.', '# Steps')
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

import yaml

FRONTMATTER_DELIMITER: Final = "---"
NAME_PATTERN: Final = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
NAME_MAX_LENGTH: Final = 64
DESCRIPTION_MAX_LENGTH: Final = 1024
COMPATIBILITY_MAX_LENGTH: Final = 500
DEFAULT_VERSION: Final = "1"
VERSION_METADATA_KEY: Final = "version"
KNOWN_FIELDS: Final = frozenset(
    {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
)


class InvalidSkillError(ValueError):
    """`SKILL.md` tidak sesuai spesifikasi. Pesannya menjelaskan field yang salah."""


@dataclass(frozen=True)
class ParsedSkill:
    """Isi `SKILL.md` yang sudah divalidasi, tanpa informasi sumber."""

    name: str
    description: str
    body: str
    version: str = DEFAULT_VERSION
    metadata: Mapping[str, str] = field(default_factory=dict)


def parse_skill_markdown(text: str, folder_name: str) -> ParsedSkill:
    """Parse dan validasi isi `SKILL.md`.

    Args:
        text: Isi file `SKILL.md`.
        folder_name: Nama folder skill, yang wajib sama dengan field `name`.

    Returns:
        Skill yang valid.

    Raises:
        InvalidSkillError: Jika frontmatter tidak ada, YAML rusak, atau field tidak valid.
    """
    frontmatter, body = _split_frontmatter(text)
    name = _required_text(frontmatter, "name", NAME_MAX_LENGTH)
    if not NAME_PATTERN.match(name):
        raise InvalidSkillError(
            f"name {name!r} must use lowercase letters, digits, and single hyphens"
        )
    if name != folder_name:
        raise InvalidSkillError(f"name {name!r} must match its folder name {folder_name!r}")
    description = _required_text(frontmatter, "description", DESCRIPTION_MAX_LENGTH)
    _optional_text(frontmatter, "compatibility", COMPATIBILITY_MAX_LENGTH)
    metadata = _metadata(frontmatter)
    return ParsedSkill(
        name=name,
        description=description,
        body=body,
        version=metadata.get(VERSION_METADATA_KEY, DEFAULT_VERSION),
        metadata=metadata,
    )


def unknown_fields(text: str) -> list[str]:
    """Field frontmatter di luar spesifikasi, untuk peringatan (tidak membuat skill tidak valid).

    >>> unknown_fields("---\\nname: a\\ndescription: b\\ntags: [x]\\n---\\n")
    ['tags']
    """
    frontmatter, _ = _split_frontmatter(text)
    return sorted(set(frontmatter) - KNOWN_FIELDS)


def _split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Pisahkan frontmatter YAML dan isi Markdown.

    Raises:
        InvalidSkillError: Jika frontmatter tidak ada atau bukan peta YAML.
    """
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        raise InvalidSkillError("SKILL.md must start with a '---' frontmatter block")
    end = _closing_delimiter_index(lines)
    try:
        loaded = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as error:
        raise InvalidSkillError(f"frontmatter is not valid YAML: {error}") from error
    if not isinstance(loaded, dict):
        raise InvalidSkillError("frontmatter must be a YAML mapping")
    body = "\n".join(lines[end + 1 :]).strip()
    return {str(key): value for key, value in loaded.items()}, body


def _closing_delimiter_index(lines: list[str]) -> int:
    """Indeks baris `---` penutup frontmatter.

    Raises:
        InvalidSkillError: Jika frontmatter tidak ditutup.
    """
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_DELIMITER:
            return index
    raise InvalidSkillError("frontmatter block is not closed with '---'")


def _required_text(frontmatter: Mapping[str, object], key: str, max_length: int) -> str:
    """Field teks wajib, tidak kosong, dan tidak melebihi `max_length`.

    Raises:
        InvalidSkillError: Jika field tidak ada, bukan teks, kosong, atau terlalu panjang.
    """
    value = frontmatter.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidSkillError(f"{key} is required and must be non-empty text")
    text = value.strip()
    if len(text) > max_length:
        raise InvalidSkillError(f"{key} must be at most {max_length} characters")
    return text


def _optional_text(frontmatter: Mapping[str, object], key: str, max_length: int) -> None:
    """Validasi field teks opsional.

    Raises:
        InvalidSkillError: Jika field ada tapi bukan teks atau terlalu panjang.
    """
    value = frontmatter.get(key)
    if value is None:
        return
    if not isinstance(value, str) or len(value) > max_length:
        raise InvalidSkillError(f"{key} must be text of at most {max_length} characters")


def _metadata(frontmatter: Mapping[str, object]) -> dict[str, str]:
    """Field `metadata` sebagai peta string ke string.

    Raises:
        InvalidSkillError: Jika `metadata` bukan peta.
    """
    value = frontmatter.get("metadata")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InvalidSkillError("metadata must be a mapping of strings")
    return {str(key): str(item) for key, item in value.items()}
