"""Dataset demo (F39): setiap pola tertanam di `planted_patterns.yaml` benar-benar ada.

Kunci jawaban ini dipakai eval F40, jadi pengecekannya dijalankan terhadap database yang di-seed
dari file SQL yang sama dengan service `demo-seed`.
"""

from pathlib import Path
from typing import Any

import psycopg
import pytest
import yaml

ANSWER_KEY = Path(__file__).resolve().parents[2] / "docker" / "demo" / "planted_patterns.yaml"


def planted_patterns() -> list[tuple[str, dict[str, Any]]]:  # Any: isi YAML bebas
    datasets = yaml.safe_load(ANSWER_KEY.read_text(encoding="utf-8"))["datasets"]
    cases: list[tuple[str, dict[str, Any]]] = []
    for dataset, spec in datasets.items():
        for pattern in spec["patterns"]:
            cases.append((dataset, pattern))
    return cases


def test_each_dataset_plants_the_same_kinds_of_patterns() -> None:
    kinds: dict[str, set[str]] = {}
    for dataset, pattern in planted_patterns():
        kinds.setdefault(dataset, set()).add(pattern["kind"])

    assert kinds["shop"] == kinds["sensors"] == {"trend", "diagnostic", "anomaly", "data-quality"}


@pytest.mark.parametrize(
    ("dataset", "pattern"),
    planted_patterns(),
    ids=[f"{dataset}-{pattern['id']}" for dataset, pattern in planted_patterns()],
)
def test_planted_pattern_is_present(
    demo_database_urls: dict[str, str],
    dataset: str,
    pattern: dict[str, Any],  # Any: isi YAML bebas
) -> None:
    with psycopg.connect(demo_database_urls[dataset]) as connection:
        row = connection.execute(pattern["check"].encode()).fetchone()

    assert row == (True,), pattern["description"]
