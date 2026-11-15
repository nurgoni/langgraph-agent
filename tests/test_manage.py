import asyncio
import io
import logging
from collections.abc import Iterator

import pytest

from agent_service import manage
from agent_service.memory.database import DatabaseEngineProvider
from agent_service.memory.users import UserRecord, UserRepository
from agent_service.service.auth import Authenticator

PASSWORD = "correct-horse"


@pytest.fixture(autouse=True)
def service_env(monkeypatch: pytest.MonkeyPatch, database_url: str) -> Iterator[None]:
    """Settings untuk perintah: database test dan FakeModel. Root logger dikembalikan setelahnya."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("USE_FAKE_MODEL", "true")
    root_logger = logging.getLogger()
    handlers, level = root_logger.handlers[:], root_logger.level
    yield
    root_logger.handlers[:] = handlers
    root_logger.setLevel(level)


def stdin_password(monkeypatch: pytest.MonkeyPatch, password: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(password + "\n"))


def find_user(database_url: str, username: str) -> UserRecord | None:
    async def lookup() -> UserRecord | None:
        async with DatabaseEngineProvider(database_url) as engine:
            return await UserRepository(engine).get_by_username(username)

    return asyncio.run(lookup(), loop_factory=asyncio.SelectorEventLoop)


def test_create_user_from_stdin_can_log_in(
    monkeypatch: pytest.MonkeyPatch, database_url: str, test_jwt_secret: str
) -> None:
    stdin_password(monkeypatch, PASSWORD)

    exit_code = manage.main(["create-user", " Alice ", "--password-stdin"])

    user = find_user(database_url, "alice")
    assert exit_code == manage.EXIT_OK
    assert user is not None
    assert user.role == "user"
    assert user.password_hash.startswith("$argon2id$")

    async def log_in() -> str:
        async with DatabaseEngineProvider(database_url) as engine:
            authenticator = Authenticator(UserRepository(engine), test_jwt_secret, 60)
            return (await authenticator.login("alice", PASSWORD)).user_id

    assert asyncio.run(log_in(), loop_factory=asyncio.SelectorEventLoop) == user.user_id


def test_service_role_account(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    stdin_password(monkeypatch, PASSWORD)

    manage.main(["create-user", "worker", "--role", "service", "--password-stdin"])

    user = find_user(database_url, "worker")
    assert user is not None
    assert user.role == "service"


def test_prompted_password_must_match(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    answers = iter([PASSWORD, "different-password"])
    monkeypatch.setattr("getpass.getpass", lambda prompt: next(answers))

    exit_code = manage.main(["create-user", "bob"])

    assert exit_code == manage.EXIT_FAILED
    assert find_user(database_url, "bob") is None


def test_prompted_password_creates_user(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    monkeypatch.setattr("getpass.getpass", lambda prompt: PASSWORD)

    assert manage.main(["create-user", "carol"]) == manage.EXIT_OK
    assert find_user(database_url, "carol") is not None


@pytest.mark.parametrize(("username", "password"), [("x", PASSWORD), ("dave", "short")])
def test_invalid_input_is_rejected(
    monkeypatch: pytest.MonkeyPatch, database_url: str, username: str, password: str
) -> None:
    stdin_password(monkeypatch, password)

    exit_code = manage.main(["create-user", username, "--password-stdin"])

    assert exit_code == manage.EXIT_FAILED
    assert find_user(database_url, username) is None


def test_duplicate_username_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    stdin_password(monkeypatch, PASSWORD)
    manage.main(["create-user", "erin", "--password-stdin"])
    stdin_password(monkeypatch, PASSWORD)

    assert manage.main(["create-user", "erin", "--password-stdin"]) == manage.EXIT_FAILED


def test_unknown_role_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exit_info:
        manage.main(["create-user", "frank", "--role", "admin"])

    assert exit_info.value.code == 2
