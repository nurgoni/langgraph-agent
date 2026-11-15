"""Perintah operator: `uv run python -m agent_service.manage <perintah>`.

    create-user <username> [--role user|service] [--password-stdin]

Akun hanya dibuat lewat CLI (FR-33), tidak ada endpoint pendaftaran. Tanpa `--password-stdin`,
password ditanya dua kali tanpa ditampilkan. Dengan `--password-stdin`, password dibaca dari baris
pertama stdin, misalnya untuk skrip atau `docker compose exec -T`.
"""

import argparse
import asyncio
import getpass
import logging
import sys
from collections.abc import Sequence
from typing import Final

from pydantic import TypeAdapter, ValidationError

from agent_service.core.logging_config import configure_logging
from agent_service.core.settings import Settings
from agent_service.memory.database import DatabaseEngineProvider
from agent_service.memory.migrator import ensure_database_migrated
from agent_service.memory.users import (
    DEFAULT_ROLE,
    USER_ROLES,
    UsernameTakenError,
    UserRecord,
    UserRepository,
    UserRole,
)
from agent_service.schema.auth import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, Username
from agent_service.service.auth import hash_password

logger = logging.getLogger(__name__)

CREATE_USER_COMMAND: Final = "create-user"
EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
PASSWORD_PROMPT: Final = "Password: "
CONFIRM_PROMPT: Final = "Repeat password: "
USERNAME_ADAPTER: Final = TypeAdapter(Username)


class InvalidUserInputError(ValueError):
    """Username atau password tidak memenuhi aturan akun."""


def build_parser() -> argparse.ArgumentParser:
    """Parser argumen CLI.

    >>> build_parser().parse_args(["create-user", "demo"]).role
    'user'
    """
    parser = argparse.ArgumentParser(prog="python -m agent_service.manage")
    commands = parser.add_subparsers(dest="command", required=True)
    create_user = commands.add_parser(CREATE_USER_COMMAND, help="Create a login account.")
    create_user.add_argument("username", help="3-32 chars: a-z, 0-9, '.', '_', '-'.")
    create_user.add_argument("--role", choices=USER_ROLES, default=DEFAULT_ROLE)
    create_user.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the password from the first line of stdin instead of prompting.",
    )
    return parser


def normalize_username(raw_username: str) -> str:
    """Validasi username dengan aturan yang sama seperti login, lalu ubah ke huruf kecil.

    >>> normalize_username(" Demo ")
    'demo'

    Raises:
        InvalidUserInputError: Jika format username tidak valid.
    """
    try:
        return USERNAME_ADAPTER.validate_python(raw_username)
    except ValidationError as error:
        raise InvalidUserInputError(
            f"Invalid username {raw_username!r}: use 3-32 characters a-z, 0-9, '.', '_', '-'"
        ) from error


def validate_password(password: str) -> str:
    """Pastikan panjang password sesuai aturan akun.

    Raises:
        InvalidUserInputError: Jika password terlalu pendek atau terlalu panjang.
    """
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise InvalidUserInputError(
            f"Password must be {PASSWORD_MIN_LENGTH}-{PASSWORD_MAX_LENGTH} characters long"
        )
    return password


def read_password(from_stdin: bool) -> str:
    """Ambil password dari stdin, atau tanya dua kali tanpa ditampilkan.

    Raises:
        InvalidUserInputError: Jika dua ketikan password berbeda.
    """
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    password = getpass.getpass(PASSWORD_PROMPT)
    if getpass.getpass(CONFIRM_PROMPT) != password:
        raise InvalidUserInputError("Passwords do not match")
    return password


async def create_user(
    database_url: str, username: str, password: str, role: UserRole
) -> UserRecord:
    """Simpan akun baru dengan password yang sudah di-hash.

    Raises:
        DatabaseNotMigratedError: Jika migrasi belum dijalankan.
        UsernameTakenError: Jika username sudah dipakai.
    """
    async with DatabaseEngineProvider(database_url) as engine:
        await ensure_database_migrated(engine)
        return await UserRepository(engine).create(username, hash_password(password), role)


def main(argv: Sequence[str] | None = None) -> int:
    """Jalankan perintah CLI.

    Function, bukan class: entrypoint CLI (AGENTS.md § Class vs Function).

    Args:
        argv: Argumen tanpa nama program. `None` berarti `sys.argv[1:]`.

    Returns:
        Exit code: 0 jika berhasil, 1 jika input ditolak atau username sudah dipakai.
    """
    args = build_parser().parse_args(argv)
    settings = Settings()
    configure_logging(settings.log_level)
    try:
        username = normalize_username(args.username)
        password = validate_password(read_password(args.password_stdin))
        user = asyncio.run(
            create_user(settings.database_url.get_secret_value(), username, password, args.role),
            loop_factory=asyncio.SelectorEventLoop,
        )
    except (InvalidUserInputError, UsernameTakenError) as error:
        logger.error("%s", error)
        return EXIT_FAILED
    logger.info("Created %s account %r (user_id %s)", user.role, user.username, user.user_id)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
