from datetime import UTC, datetime
from pathlib import Path

from agent_service.evals.report import (
    CaseResult,
    DatasetReport,
    EvalReport,
    render_markdown,
    write_report,
)
from agent_service.evals.scoring import CheckResult

STARTED = datetime(2026, 11, 17, 9, 30, tzinfo=UTC)


def report() -> EvalReport:
    passed = CaseResult(
        case_id="ok-case",
        passed=True,
        checks=[],
        reply="fine",
        latency_seconds=1.25,
        input_tokens=50,
        output_tokens=5,
    )
    failed = CaseResult(
        case_id="bad-case",
        passed=False,
        checks=[
            CheckResult(name="contains: Tokyo", passed=False),
            CheckResult(name="tool not called: load_skill", passed=True),
        ],
        reply="Kyoto",
    )
    errored = CaseResult(case_id="http-case", passed=False, checks=[], error="404 Not Found")
    dataset = DatasetReport(name="skills", model="qwen", cases=[passed, failed, errored])
    return EvalReport(started_at=STARTED, agent_url="http://agent", datasets=[dataset])


def test_markdown_summarizes_scores_and_explains_failures() -> None:
    text = render_markdown(report())

    assert "## skills: 1/3 (33%)" in text
    assert "| ok-case | pass | 1.2s | 50/5 |" in text
    assert "| bad-case | **fail** | - | -/- |" in text
    assert "- failed contains: Tokyo" in text
    assert "tool not called" not in text
    assert "- error: 404 Not Found" in text
    assert "### ok-case" not in text


def test_report_is_written_as_json_and_markdown(tmp_path: Path) -> None:
    json_path, markdown_path = write_report(report(), tmp_path / "out")

    assert json_path.name == "eval-20261117-093000.json"
    loaded = EvalReport.model_validate_json(json_path.read_text(encoding="utf-8"))
    assert loaded.datasets[0].score == 1 / 3
    assert markdown_path.read_text(encoding="utf-8").startswith("# Eval report 2026-11-17 09:30")
    assert not report().all_passed
