"""`DataSourceRegistry` dan `load_entries` (FR-51): file registry, DSN dari env, status."""

from pathlib import Path

import pytest

from agent_service.core.env import EnvReader
from agent_service.datasource.model import (
    DataSourceEntry,
    DataSourceNotFoundError,
    DataSourceUnavailableError,
)
from agent_service.datasource.registry import (
    DataSourceRegistry,
    InvalidDataSourcesFileError,
    load_entries,
)

REPO_REGISTRY = Path(__file__).resolve().parents[2] / "datasources.yaml"
# Port 1 di loopback: koneksi langsung ditolak, tanpa menunggu timeout.
UNREACHABLE_URL = "postgresql://nobody:nothing@127.0.0.1:1/none"


def entry(data_source_id: str, url_env: str) -> DataSourceEntry:
    return DataSourceEntry(id=data_source_id, description=f"{data_source_id} data", url_env=url_env)


def test_repo_registry_lists_both_demo_datasets_by_env_name() -> None:
    entries = load_entries(REPO_REGISTRY)

    assert [(e.id, e.url_env) for e in entries] == [
        ("shop", "DEMO_SHOP_DATABASE_URL"),
        ("sensors", "DEMO_SENSORS_DATABASE_URL"),
    ]


def test_missing_registry_file_means_no_data_sources(tmp_path: Path) -> None:
    assert load_entries(tmp_path / "absent.yaml") == []


@pytest.mark.parametrize(
    "content",
    [
        "data_sources: [",
        "data_sources:\n  - id: Bad Id\n    description: x\n    url_env: X\n",
        "data_sources:\n  - id: a\n    description: x\n    url_env: X\n    url: postgres://\n",
        "data_sources:\n  - {id: a, description: x, url_env: X}\n"
        "  - {id: a, description: y, url_env: Y}\n",
    ],
)
def test_broken_registry_file_fails_with_a_clear_error(tmp_path: Path, content: str) -> None:
    path = tmp_path / "datasources.yaml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(InvalidDataSourcesFileError, match=str(path).replace("\\", "\\\\")):
        load_entries(path)


async def test_open_marks_missing_env_and_unreachable_databases_unavailable(
    demo_database_urls: dict[str, str],
) -> None:
    env = EnvReader(
        environ={"SHOP_URL": demo_database_urls["shop"], "DOWN_URL": UNREACHABLE_URL},
        env_file=None,
    )
    registry = DataSourceRegistry(
        [entry("shop", "SHOP_URL"), entry("down", "DOWN_URL"), entry("unset", "UNSET_URL")],
        env,
        timeout_seconds=5,
    )

    await registry.open()
    try:
        statuses = {status.id: status for status in registry.statuses()}
        assert statuses["shop"].available and statuses["shop"].error is None
        assert statuses["down"].error == "Cannot connect to the database."
        assert statuses["unset"].error == "Environment variable UNSET_URL is not set."
        assert "nothing" not in str(statuses["down"])
        result = await registry.get("shop").fetch("SELECT count(*) FROM orders")
        assert result.rows[0][0] == 22045
        with pytest.raises(DataSourceUnavailableError, match="UNSET_URL"):
            registry.get("unset")
        with pytest.raises(DataSourceNotFoundError):
            registry.get("other")
    finally:
        await registry.close()


def test_statuses_can_be_limited_to_project_ids() -> None:
    registry = DataSourceRegistry(
        [entry("a", "A_URL"), entry("b", "B_URL")], EnvReader(environ={}, env_file=None), 5
    )

    assert [status.id for status in registry.statuses(["b", "unknown"])] == ["b"]
    assert registry.contains("a") and not registry.contains("c")
    assert registry.statuses()[0].error == "The data source has not been opened yet."
