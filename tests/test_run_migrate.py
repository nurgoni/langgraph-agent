import pytest

from agent_service import run_migrate

DATABASE_URL = "postgresql://agent:agent@127.0.0.1:5432/migrate_test"


def test_main_migrates_database_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_FAKE_MODEL", "true")
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    migrated: list[str] = []

    async def fake_upgrade(database_url: str) -> None:
        migrated.append(database_url)

    monkeypatch.setattr(run_migrate, "upgrade_database", fake_upgrade)

    run_migrate.main()

    assert migrated == [DATABASE_URL]
