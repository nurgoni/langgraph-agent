"""Runner eval terhadap service in-process (FakeModel), lewat `AgentClient` asli."""

from pathlib import Path

from agent_service.client import AgentClient
from agent_service.evals.dataset import EvalCase, EvalDataset, Expectations, load_dataset
from agent_service.evals.report import write_report
from agent_service.evals.runner import EvalRunner
from agent_service.llm.fake import DEFAULT_FAKE_RESPONSE
from agent_service.run_evals import run_datasets

SMOKE = Path(__file__).resolve().parents[2] / "evals" / "smoke.yaml"


async def test_cases_are_scored_with_reply_trace_and_history(eval_client: AgentClient) -> None:
    dataset = EvalDataset(
        name="demo",
        agent="chatbot",
        cases=[
            EvalCase(id="pass", input="Halo", expect=Expectations(contains=["fake model"])),
            EvalCase(id="fail", input="Halo", expect=Expectations(contains=["Tokyo"])),
        ],
    )

    report = await EvalRunner(eval_client).run(dataset)

    passing, failing = report.cases
    assert (report.passed, report.total) == (1, 2)
    assert passing.reply == DEFAULT_FAKE_RESPONSE
    assert passing.run_id is not None
    assert passing.latency_seconds is not None
    assert [check.passed for check in failing.checks] == [False]


async def test_http_errors_fail_only_their_case(eval_client: AgentClient) -> None:
    dataset = EvalDataset(
        name="demo",
        cases=[
            EvalCase(id="unknown-agent", input="Halo", agent="ghost"),
            EvalCase(id="unknown-project", input="Halo", project="ghost"),
            EvalCase(id="default-agent", input="Halo"),
        ],
    )

    report = await EvalRunner(eval_client).run(dataset)

    assert [case.passed for case in report.cases] == [False, False, True]
    assert "404" in (report.cases[0].error or "")
    assert eval_client.project_id is None


async def test_unknown_model_is_reported_per_case(eval_client: AgentClient) -> None:
    dataset = EvalDataset(name="demo", cases=[EvalCase(id="hi", input="Halo")])

    report = await EvalRunner(eval_client, model="not-allowed").run(dataset)

    assert report.model == "not-allowed"
    assert "422" in (report.cases[0].error or "")


async def test_report_reflects_case_results(eval_client: AgentClient, tmp_path: Path) -> None:
    report = await run_datasets(eval_client, [load_dataset(SMOKE)], None, "http://testserver")

    json_path, _ = write_report(report, tmp_path)

    assert report.all_passed
    assert json_path.exists()
