from pathlib import Path

import pytest

from agent_service.evals.dataset import DatasetError, EvalDataset, load_dataset

VALID = """
name: demo
agent: chatbot
cases:
  - id: hello
    input: "Halo"
    expect:
      contains: ["halo"]
      max_latency_seconds: 10
  - id: in-project
    input: "Hi"
    project: general-assistant
    agent: research-assistant
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "dataset.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_dataset_is_loaded_with_case_overrides(tmp_path: Path) -> None:
    dataset = load_dataset(write(tmp_path, VALID))

    first, second = dataset.cases
    assert first.expect.contains == ["halo"]
    assert dataset.target_for(first) == ("chatbot", None)
    assert dataset.target_for(second) == ("research-assistant", "general-assistant")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("name: x\ncases: []\n", "cases"),
        ("name: x\ncases:\n  - {id: a, input: b}\n  - {id: a, input: c}\n", "Duplicate"),
        ("name: x\ncases:\n  - {id: a, input: b, expect: {contain: [x]}}\n", "contain"),
        ("name: x\ncases:\n  - {id: Bad Id, input: b}\n", "id"),
        ("name: [unclosed\n", "Cannot read"),
    ],
)
def test_invalid_datasets_are_rejected(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(DatasetError, match=message):
        load_dataset(write(tmp_path, text))


def test_missing_file_is_a_dataset_error(tmp_path: Path) -> None:
    with pytest.raises(DatasetError, match="Cannot read"):
        load_dataset(tmp_path / "missing.yaml")


def test_dataset_needs_a_name() -> None:
    with pytest.raises(ValueError, match="name"):
        EvalDataset.model_validate({"cases": [{"id": "a", "input": "b"}]})
