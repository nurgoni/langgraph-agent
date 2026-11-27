from pathlib import Path

from agent_service.core.env import EnvReader


def test_process_env_wins_over_env_file_and_empty_counts_as_unset(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FROM_FILE=file\nBOTH=file\nEMPTY_IN_PROCESS=file\n", encoding="utf-8")

    reader = EnvReader(environ={"BOTH": "process", "EMPTY_IN_PROCESS": ""}, env_file=env_file)

    assert reader.get("FROM_FILE") == "file"
    assert reader.get("BOTH") == "process"
    assert reader.get("EMPTY_IN_PROCESS") == "file"
    assert reader.get("MISSING") is None


def test_missing_env_file_is_ignored(tmp_path: Path) -> None:
    reader = EnvReader(environ={}, env_file=tmp_path / "absent.env")

    assert reader.get("ANYTHING") is None
