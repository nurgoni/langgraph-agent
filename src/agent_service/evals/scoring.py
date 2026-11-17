"""Skor deterministik satu kasus eval (FR-41). LLM judge ditunda (keputusan user F31).

Setiap cek adalah transformasi murni dari `Observation` ke `CheckResult`, jadi ditulis sebagai
function (AGENTS.md § Class vs Function).

>>> observation = Observation(reply="Tokyo is the capital.", tool_calls=[], latency_seconds=2.0)
>>> [check.passed for check in score_case(Expectations(contains=["tokyo"]), observation)]
[True]
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

from pydantic import BaseModel

from agent_service.evals.dataset import Expectations
from agent_service.schema.responses import ChatMessage, ToolCall
from agent_service.schema.traces import RunTrace

LOAD_SKILL_TOOL: Final = "load_skill"
SKILL_NAME_ARG: Final = "name"
AI_MESSAGE_TYPE: Final = "ai"


class CheckResult(BaseModel):
    """Hasil satu cek."""

    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class Observation:
    """Yang terlihat dari satu run: jawaban, tool call, latensi, dan token."""

    reply: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    latency_seconds: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None


def observe(
    reply: ChatMessage,
    history: Sequence[ChatMessage],
    trace: RunTrace | None,
    wall_seconds: float,
) -> Observation:
    """Susun observasi dari jawaban, riwayat thread, dan trace run.

    Latensi diambil dari trace (waktu di service). Tanpa trace, dipakai waktu yang diukur runner.
    """
    tool_calls: list[ToolCall] = []
    for message in history:
        if message.type == AI_MESSAGE_TYPE:
            tool_calls.extend(message.tool_calls)
    latency = wall_seconds if trace is None else trace.duration_ms / 1000
    return Observation(
        reply=reply.content,
        tool_calls=tool_calls,
        latency_seconds=latency,
        input_tokens=None if trace is None else trace.input_tokens,
        output_tokens=None if trace is None else trace.output_tokens,
    )


def loaded_skills(tool_calls: Sequence[ToolCall]) -> list[str]:
    """Nama skill yang dimuat lewat `load_skill`.

    >>> loaded_skills([ToolCall(name="load_skill", args={"name": "meeting-notes"})])
    ['meeting-notes']
    """
    names: list[str] = []
    for call in tool_calls:
        skill = call.args.get(SKILL_NAME_ARG)
        if call.name == LOAD_SKILL_TOOL and isinstance(skill, str):
            names.append(skill)
    return names


def score_case(expect: Expectations, observation: Observation) -> list[CheckResult]:
    """Jalankan semua cek yang diisi di `expect`, urut sesuai field."""
    called = [call.name for call in observation.tool_calls]
    skills = loaded_skills(observation.tool_calls)
    reply = observation.reply.casefold()
    checks: list[CheckResult] = []
    for text in expect.contains:
        checks.append(CheckResult(name=f"contains: {text}", passed=text.casefold() in reply))
    for text in expect.not_contains:
        checks.append(
            CheckResult(name=f"not contains: {text}", passed=text.casefold() not in reply)
        )
    for tool in expect.tools_called:
        checks.append(_membership(f"tool called: {tool}", tool in called, called))
    for tool in expect.tools_not_called:
        checks.append(_membership(f"tool not called: {tool}", tool not in called, called))
    for skill in expect.skills_loaded:
        checks.append(_membership(f"skill loaded: {skill}", skill in skills, skills))
    if expect.max_latency_seconds is not None:
        checks.append(latency_check(expect.max_latency_seconds, observation.latency_seconds))
    return checks


def latency_check(limit_seconds: float, latency_seconds: float) -> CheckResult:
    """Lolos jika latensi tidak melebihi batas.

    >>> latency_check(10, 12.5).detail
    '12.5s (limit 10s)'
    """
    return CheckResult(
        name=f"latency <= {limit_seconds:g}s",
        passed=latency_seconds <= limit_seconds,
        detail=f"{latency_seconds:.1f}s (limit {limit_seconds:g}s)",
    )


def _membership(name: str, passed: bool, observed: list[str]) -> CheckResult:
    """Cek keanggotaan dengan daftar yang teramati sebagai detail."""
    return CheckResult(name=name, passed=passed, detail=f"observed: {observed or 'none'}")
