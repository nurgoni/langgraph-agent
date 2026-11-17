"""Dataset di `evals/` valid, dan smoke eval lolos dengan FakeModel (smoke eval CI, F31)."""

from pathlib import Path

import pytest

from agent_service.client import AgentClient
from agent_service.evals.dataset import load_dataset
from agent_service.evals.runner import EvalRunner

DATASETS_DIR = Path(__file__).resolve().parents[2] / "evals"
DATASET_FILES = sorted(DATASETS_DIR.glob("*.yaml"))


def test_datasets_exist() -> None:
    assert {path.name for path in DATASET_FILES} >= {"smoke.yaml", "skills.yaml"}


@pytest.mark.parametrize("path", DATASET_FILES, ids=lambda path: path.name)
def test_every_dataset_is_valid(path: Path) -> None:
    assert load_dataset(path).cases


async def test_smoke_dataset_passes_with_the_fake_model(eval_client: AgentClient) -> None:
    report = await EvalRunner(eval_client).run(load_dataset(DATASETS_DIR / "smoke.yaml"))

    failures = [(case.case_id, case.error, case.checks) for case in report.cases if not case.passed]
    assert failures == []
