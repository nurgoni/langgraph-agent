"""Laporan eval: hasil per kasus, skor per dataset, dan file JSON + Markdown (FR-41).

Laporan dari model asli tidak di-commit (folder default `eval-reports/` ada di `.gitignore`).

>>> case = CaseResult(case_id="hi", passed=True, checks=[], reply="Halo")
>>> report = DatasetReport(name="demo", model=None, cases=[case])
>>> report.passed, report.total, report.score
(1, 1, 1.0)
"""

from datetime import datetime
from pathlib import Path
from typing import Final

from pydantic import BaseModel, computed_field

from agent_service.evals.scoring import CheckResult

REPLY_EXCERPT_CHARS: Final = 300
TIMESTAMP_FORMAT: Final = "%Y%m%d-%H%M%S"


class CaseResult(BaseModel):
    """Hasil satu kasus. `error` terisi jika request ke service gagal."""

    case_id: str
    passed: bool
    checks: list[CheckResult]
    reply: str = ""
    run_id: str | None = None
    latency_seconds: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None


class DatasetReport(BaseModel):
    """Hasil satu dataset."""

    name: str
    model: str | None
    cases: list[CaseResult]

    @computed_field
    @property
    def passed(self) -> int:
        """Jumlah kasus yang lolos."""
        return sum(1 for case in self.cases if case.passed)

    @computed_field
    @property
    def total(self) -> int:
        """Jumlah kasus."""
        return len(self.cases)

    @computed_field
    @property
    def score(self) -> float:
        """Proporsi kasus yang lolos, 0–1."""
        return self.passed / self.total if self.cases else 0.0


class EvalReport(BaseModel):
    """Semua dataset dalam satu kali `run_evals`."""

    started_at: datetime
    agent_url: str
    datasets: list[DatasetReport]

    @property
    def all_passed(self) -> bool:
        """Semua kasus di semua dataset lolos."""
        return all(report.passed == report.total for report in self.datasets)


def excerpt(text: str) -> str:
    """Potongan jawaban untuk laporan.

    >>> excerpt("a" * 400).endswith("…")
    True
    """
    if len(text) <= REPLY_EXCERPT_CHARS:
        return text
    return text[:REPLY_EXCERPT_CHARS] + "…"


def render_markdown(report: EvalReport) -> str:
    """Laporan untuk dibaca manusia: ringkasan per dataset, lalu kasus yang gagal."""
    lines = [
        f"# Eval report {report.started_at:%Y-%m-%d %H:%M}",
        "",
        f"Service: {report.agent_url}",
    ]
    for dataset in report.datasets:
        lines.extend(
            ["", f"## {dataset.name}: {dataset.passed}/{dataset.total} ({dataset.score:.0%})"]
        )
        lines.extend(["", "| Case | Result | Latency | Tokens in/out |", "|---|---|---|---|"])
        for case in dataset.cases:
            lines.append(_case_row(case))
        for case in dataset.cases:
            lines.extend(_failure_lines(case))
    return "\n".join(lines) + "\n"


def write_report(report: EvalReport, output_dir: Path) -> tuple[Path, Path]:
    """Tulis laporan sebagai `eval-<waktu>.json` dan `.md` di `output_dir`.

    Returns:
        Path file JSON dan Markdown.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"eval-{report.started_at.strftime(TIMESTAMP_FORMAT)}"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def _case_row(case: CaseResult) -> str:
    """Satu baris tabel ringkasan."""
    result = "pass" if case.passed else "**fail**"
    latency = "-" if case.latency_seconds is None else f"{case.latency_seconds:.1f}s"
    tokens = f"{_number(case.input_tokens)}/{_number(case.output_tokens)}"
    return f"| {case.case_id} | {result} | {latency} | {tokens} |"


def _failure_lines(case: CaseResult) -> list[str]:
    """Detail kasus yang gagal: error, cek yang gagal, dan potongan jawaban."""
    if case.passed:
        return []
    lines = ["", f"### {case.case_id}"]
    if case.error:
        lines.append(f"- error: {case.error}")
    for check in case.checks:
        if not check.passed:
            lines.append(f"- failed {check.name} {check.detail}".rstrip())
    lines.append(f"- reply: {excerpt(case.reply)!r}")
    return lines


def _number(value: int | None) -> str:
    """Angka atau tanda `-` jika tidak diketahui."""
    return "-" if value is None else str(value)
