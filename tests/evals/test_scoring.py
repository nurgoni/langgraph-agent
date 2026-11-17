from dataclasses import replace
from datetime import UTC, datetime

from agent_service.evals.dataset import Expectations
from agent_service.evals.scoring import Observation, observe, score_case
from agent_service.schema.responses import ChatMessage, ToolCall
from agent_service.schema.traces import RunTrace

NOW = datetime(2026, 11, 17, tzinfo=UTC)
SKILL_CALL = ToolCall(name="load_skill", args={"name": "meeting-notes"}, id="c1")


BASE_OBSERVATION = Observation(
    reply="## Decisions\n- Ship it\n## Action items",
    tool_calls=[SKILL_CALL],
    latency_seconds=12.0,
)


def observation(tool_calls: list[ToolCall] | None = None) -> Observation:
    if tool_calls is None:
        return BASE_OBSERVATION
    return replace(BASE_OBSERVATION, tool_calls=tool_calls)


def results(expect: Expectations, seen: Observation) -> dict[str, bool]:
    return {check.name: check.passed for check in score_case(expect, seen)}


def test_every_filled_expectation_becomes_one_check() -> None:
    expect = Expectations(
        contains=["DECISIONS", "risks"],
        not_contains=["lorem"],
        tools_called=["load_skill"],
        tools_not_called=["save_memory"],
        skills_loaded=["meeting-notes", "research-report"],
        max_latency_seconds=10,
    )

    assert results(expect, observation()) == {
        "contains: DECISIONS": True,
        "contains: risks": False,
        "not contains: lorem": True,
        "tool called: load_skill": True,
        "tool not called: save_memory": True,
        "skill loaded: meeting-notes": True,
        "skill loaded: research-report": False,
        "latency <= 10s": False,
    }


def test_empty_expectations_have_no_checks() -> None:
    assert score_case(Expectations(), observation()) == []


def test_failed_membership_reports_what_was_observed() -> None:
    [check] = score_case(Expectations(tools_called=["web_search"]), observation(tool_calls=[]))

    assert check.detail == "observed: none"


def test_observe_reads_tool_calls_from_ai_messages_and_latency_from_trace() -> None:
    history = [
        ChatMessage(type="human", content="notes"),
        ChatMessage(type="ai", content="", tool_calls=[SKILL_CALL]),
        ChatMessage(type="tool", content="skill body", tool_call_id="c1"),
        ChatMessage(type="ai", content="done"),
    ]
    trace = RunTrace(
        run_id="r1",
        thread_id="t1",
        agent_id="chatbot",
        project_id=None,
        status="ok",
        started_at=NOW,
        ended_at=NOW,
        duration_ms=2500,
        input_tokens=90,
        output_tokens=12,
        spans=[],
    )

    traced = observe(history[-1], history, trace, wall_seconds=9.0)
    untraced = observe(history[-1], history, None, wall_seconds=9.0)

    assert traced.tool_calls == [SKILL_CALL]
    assert (traced.latency_seconds, traced.input_tokens, traced.output_tokens) == (2.5, 90, 12)
    assert (untraced.latency_seconds, untraced.input_tokens) == (9.0, None)
