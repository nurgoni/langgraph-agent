"""Entrypoint: `uv run python -m agent_service.run_evals evals/smoke.yaml [...]` (FR-41).

Menjalankan dataset eval terhadap service yang sedang berjalan (`AGENT_URL`) dengan akun
`EVAL_USERNAME`/`EVAL_PASSWORD`, lalu menulis laporan JSON + Markdown.

Exit code: 0 jika semua kasus lolos, 1 jika ada kasus gagal, 2 jika dataset atau konfigurasi
tidak valid, atau login gagal.
"""

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from agent_service.client import AgentClient, AgentClientError
from agent_service.evals.dataset import DatasetError, EvalDataset, load_dataset
from agent_service.evals.report import EvalReport, write_report
from agent_service.evals.runner import EvalRunner
from agent_service.evals.settings import EvalSettings

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR: Final = Path("eval-reports")
EXIT_OK: Final = 0
EXIT_CASES_FAILED: Final = 1
EXIT_USAGE_ERROR: Final = 2
LOG_FORMAT: Final = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
MISSING_CREDENTIALS: Final = (
    "Set EVAL_USERNAME and EVAL_PASSWORD (create a service account with "
    "`python -m agent_service.manage create-user <name> --role service`)."
)


def build_parser() -> argparse.ArgumentParser:
    """Parser argumen CLI.

    >>> args = build_parser().parse_args(["evals/smoke.yaml", "--model", "fake"])
    >>> [path.name for path in args.datasets], args.model, args.output_dir.name
    (['smoke.yaml'], 'fake', 'eval-reports')
    """
    parser = argparse.ArgumentParser(prog="run_evals", description="Run agent eval datasets.")
    parser.add_argument("datasets", nargs="+", type=Path, help="Dataset YAML files.")
    parser.add_argument("--model", help="Model for every case (default: project or service).")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


async def run_datasets(
    client: AgentClient, datasets: Sequence[EvalDataset], model: str | None, agent_url: str
) -> EvalReport:
    """Jalankan semua dataset dengan satu client yang sudah login."""
    runner = EvalRunner(client, model)
    started_at = datetime.now(UTC)
    reports = [await runner.run(dataset) for dataset in datasets]
    return EvalReport(started_at=started_at, agent_url=agent_url, datasets=reports)


async def run_cli(argv: Sequence[str] | None = None, settings: EvalSettings | None = None) -> int:
    """Baca argumen dan settings, jalankan eval, tulis laporan, lalu kembalikan exit code."""
    args = build_parser().parse_args(argv)
    resolved = EvalSettings() if settings is None else settings
    try:
        datasets = [load_dataset(path) for path in args.datasets]
    except DatasetError as error:
        logger.error("%s", error)
        return EXIT_USAGE_ERROR
    if resolved.eval_username is None or resolved.eval_password is None:
        logger.error(MISSING_CREDENTIALS)
        return EXIT_USAGE_ERROR
    async with AgentClient(resolved.agent_url, timeout=resolved.eval_timeout_seconds) as client:
        try:
            await client.alogin(resolved.eval_username, resolved.eval_password.get_secret_value())
        # ValidationError: username tidak lolos schema login, sebelum request dikirim.
        except (AgentClientError, ValidationError) as error:
            logger.error("Login to %s failed: %s", resolved.agent_url, error)
            return EXIT_USAGE_ERROR
        report = await run_datasets(client, datasets, args.model, resolved.agent_url)
    json_path, markdown_path = write_report(report, args.output_dir)
    for dataset in report.datasets:
        logger.info("%s: %d/%d passed", dataset.name, dataset.passed, dataset.total)
    logger.info("Report written to %s and %s", json_path, markdown_path)
    return EXIT_OK if report.all_passed else EXIT_CASES_FAILED


def main() -> None:
    """Entrypoint CLI. Function, bukan class (AGENTS.md § Class vs Function)."""
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    sys.exit(asyncio.run(run_cli()))


if __name__ == "__main__":
    main()
