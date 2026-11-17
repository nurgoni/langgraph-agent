from pathlib import Path

import pytest
from pydantic import SecretStr

from agent_service.evals.settings import EvalSettings
from agent_service.run_evals import EXIT_USAGE_ERROR, run_cli

SMOKE = Path(__file__).resolve().parents[1] / "evals" / "smoke.yaml"
# Port 1 di loopback: koneksi ditolak.
UNREACHABLE_URL = "http://127.0.0.1:1"
TIMEOUT_SECONDS = 2.0


def settings(username: str | None = None, password: str | None = None) -> EvalSettings:
    return EvalSettings(
        _env_file=None,
        agent_url=UNREACHABLE_URL,
        eval_username=username,
        eval_password=None if password is None else SecretStr(password),
        eval_timeout_seconds=TIMEOUT_SECONDS,
    )


async def test_missing_credentials_exit_with_usage_error(caplog: pytest.LogCaptureFixture) -> None:
    code = await run_cli([str(SMOKE)], settings())

    assert code == EXIT_USAGE_ERROR
    assert "EVAL_USERNAME" in caplog.text


async def test_invalid_dataset_exits_before_contacting_the_service(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("name: x\ncases: []\n", encoding="utf-8")

    code = await run_cli([str(broken)], settings("evals", "secret"))

    assert code == EXIT_USAGE_ERROR


@pytest.mark.parametrize("username", ["evals", "Not Valid"])
async def test_failed_login_exits_with_usage_error(
    caplog: pytest.LogCaptureFixture, username: str
) -> None:
    code = await run_cli([str(SMOKE)], settings(username, "secret"))

    assert code == EXIT_USAGE_ERROR
    assert "Login to" in caplog.text
