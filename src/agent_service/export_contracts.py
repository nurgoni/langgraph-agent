"""Entrypoint: `uv run python -m agent_service.export_contracts [--check] [--output-dir DIR]`.

Tanpa `--check`, file di `contracts/` ditulis ulang dari kode. Dengan `--check`, tidak ada file
yang ditulis: exit code 1 jika ada kontrak yang tidak sinkron (dipakai CI).
"""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from agent_service.core.logging_config import configure_logging
from agent_service.service.contracts import build_contracts, stale_contracts, write_contracts

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR: Final = Path("contracts")
EXPORT_COMMAND: Final = "uv run python -m agent_service.export_contracts"
EXIT_OK: Final = 0
EXIT_STALE: Final = 1


def build_parser() -> argparse.ArgumentParser:
    """Parser argumen CLI.

    >>> args = build_parser().parse_args(["--check"])
    >>> args.check, args.output_dir == DEFAULT_OUTPUT_DIR
    (True, True)
    """
    parser = argparse.ArgumentParser(prog="python -m agent_service.export_contracts")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write files; exit with 1 if contracts/ is out of date.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Export atau periksa kontrak API.

    Function, bukan class: entrypoint CLI (AGENTS.md § Class vs Function).

    Args:
        argv: Argumen tanpa nama program. `None` berarti `sys.argv[1:]`.

    Returns:
        Exit code: 0 jika berhasil atau sinkron, 1 jika `--check` menemukan kontrak usang.
    """
    args = build_parser().parse_args(argv)
    configure_logging("INFO")
    contracts = build_contracts()
    if not args.check:
        write_contracts(args.output_dir, contracts)
        logger.info("Wrote %d contract files to %s", len(contracts), args.output_dir)
        return EXIT_OK
    stale = stale_contracts(args.output_dir, contracts)
    if stale:
        logger.error(
            "API contracts are out of date: %s. Run `%s` and commit the result.",
            ", ".join(stale),
            EXPORT_COMMAND,
        )
        return EXIT_STALE
    logger.info("API contracts in %s are up to date", args.output_dir)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
