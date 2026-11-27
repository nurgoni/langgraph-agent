"""Shared pytest fixtures. Feature-specific fixtures live next to their tests."""

import asyncio
import ipaddress
import os
import socket
import uuid
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import LiteralString

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import make_url

from agent_service.core.constants import DEFAULT_DATABASE_URL
from agent_service.memory.migrator import upgrade_database

INTEGRATION_MARKER = "integration"
LOCALHOST_NAME = "localhost"

# Server Postgres untuk test. Default = service `postgres` dari compose.yaml.
TEST_DATABASE_URL_ENV = "TEST_DATABASE_URL"
TEST_DATABASE_PREFIX = "agent_service_test_"
ADMIN_CONNECT_TIMEOUT_SECONDS = 5
# Tabel migrasi tidak dikosongkan, supaya database test tetap tercatat sudah dimigrasi.
KEPT_TABLES = ("alembic_version", "checkpoint_migrations", "store_migrations")
# Settings dari test yang lupa memakai fixture `database_url` gagal di sini, bukan menulis ke
# database dev.
UNCONFIGURED_DATABASE_URL = "postgresql://test-database-not-configured.invalid/none"
# JWT_SECRET wajib di Settings. Test yang membuat Settings tanpa argumen memakai nilai ini.
TEST_JWT_SECRET = "test-jwt-secret-with-at-least-32-chars"


class NetworkAccessError(RuntimeError):
    """Unit test mencoba membuka koneksi ke host di luar loopback."""


def _is_loopback(address: object) -> bool:
    """Cek apakah alamat `connect()` menuju loopback.

    Args:
        address: Argumen `address` milik `socket.connect`, biasanya tuple `(host, port)`.

    Returns:
        True jika host adalah `localhost` atau IP loopback.
    """
    if not isinstance(address, tuple) or not address:
        return False
    host = str(address[0])
    if host == LOCALHOST_NAME:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def block_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Gagalkan setiap koneksi keluar di unit test (AGENTS.md § Testing).

    Loopback tetap diizinkan karena event loop asyncio di Windows memakainya secara internal.
    Test bertanda `integration` dikecualikan.
    """
    if request.node.get_closest_marker(INTEGRATION_MARKER) is not None:
        yield
        return
    original_connect = socket.socket.connect

    def guarded_connect(sock: socket.socket, address: object) -> None:
        if not _is_loopback(address):
            raise NetworkAccessError(f"network access is blocked in unit tests: {address!r}")
        original_connect(sock, address)  # pyrefly: ignore[bad-argument-type]

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    yield


def pytest_asyncio_loop_factories(config: pytest.Config, item: pytest.Item) -> Mapping[str, object]:
    """Jalankan test async di `SelectorEventLoop`.

    psycopg async tidak bisa memakai `ProactorEventLoop`, loop default di Windows.
    """
    return {"selector": asyncio.SelectorEventLoop}


@pytest.fixture(autouse=True)
def isolate_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Arahkan `DATABASE_URL` ke host yang tidak ada, supaya test tidak pernah menyentuh DB dev."""
    monkeypatch.setenv("DATABASE_URL", UNCONFIGURED_DATABASE_URL)


@pytest.fixture(autouse=True)
def isolate_data_sources(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Tanpa data source di test, kecuali test mengisinya sendiri.

    `datasources.yaml` repo dan DSN demo di `.env` developer tidak pernah terbaca (F39).
    """
    monkeypatch.setenv("DATA_SOURCES_FILE", str(tmp_path / "no-data-sources.yaml"))


@pytest.fixture(autouse=True)
def artifact_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Arahkan `ARTIFACT_DIR` ke folder sementara per test, supaya file tidak ditulis ke repo."""
    directory = tmp_path / "artifacts"
    monkeypatch.setenv("ARTIFACT_DIR", str(directory))
    return directory


@pytest.fixture(autouse=True)
def test_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    """Isi `JWT_SECRET` dengan nilai test, supaya `Settings()` di test tidak membaca `.env` dev."""
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    return TEST_JWT_SECRET


@pytest.fixture(scope="session")
def postgres_database() -> Iterator[str]:
    """Database Postgres baru untuk satu sesi test, sudah dimigrasi, lalu dihapus di akhir sesi.

    Server diambil dari `TEST_DATABASE_URL`, atau Postgres dari compose.yaml jika kosong.
    """
    server_url = os.environ.get(TEST_DATABASE_URL_ENV) or DEFAULT_DATABASE_URL
    database_name = f"{TEST_DATABASE_PREFIX}{uuid.uuid4().hex[:8]}"
    _run_admin_statement(server_url, "CREATE DATABASE {}", database_name)
    database_url = (
        make_url(server_url).set(database=database_name).render_as_string(hide_password=False)
    )
    try:
        asyncio.run(upgrade_database(database_url), loop_factory=asyncio.SelectorEventLoop)
        yield database_url
    finally:
        _run_admin_statement(server_url, "DROP DATABASE IF EXISTS {} WITH (FORCE)", database_name)


@pytest.fixture
def database_url(postgres_database: str) -> str:
    """URL database test yang dikosongkan sebelum setiap test, supaya ID thread tidak bentrok."""
    with psycopg.connect(postgres_database, autocommit=True) as connection:
        rows = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
        tables = [row[0] for row in rows if row[0] not in KEPT_TABLES]
        if tables:
            identifiers = sql.SQL(", ").join(sql.Identifier(name) for name in tables)
            connection.execute(sql.SQL("TRUNCATE {}").format(identifiers))
    return postgres_database


def _run_admin_statement(server_url: str, template: LiteralString, database_name: str) -> None:
    """Jalankan `CREATE`/`DROP DATABASE` di server test, atau gagal cepat dengan petunjuk.

    Raises:
        pytest.fail.Exception: Jika server Postgres tidak terjangkau.
    """
    try:
        with psycopg.connect(
            server_url, autocommit=True, connect_timeout=ADMIN_CONNECT_TIMEOUT_SECONDS
        ) as connection:
            connection.execute(sql.SQL(template).format(sql.Identifier(database_name)))
    except psycopg.OperationalError as error:
        location = make_url(server_url).render_as_string(hide_password=True)
        pytest.fail(
            f"Postgres for tests is not reachable at {location} ({error}). "
            f"Run `docker compose up -d postgres`, or set {TEST_DATABASE_URL_ENV}.",
            pytrace=False,
        )


DEMO_DIR = Path(__file__).resolve().parents[1] / "docker" / "demo"
DEMO_DATASET_NAMES = ("shop", "sensors")
DEMO_ROLE_PREFIX = "agent_ro_test_"


@pytest.fixture(scope="session")
def demo_database_urls() -> Iterator[dict[str, str]]:
    """Dua dataset demo (F39) di database sementara, dengan DSN milik user read-only acak.

    Isi dan hak akses sama dengan service `demo-seed` (`docker/demo/`). Role dan database
    dihapus di akhir sesi. Kunci hasil adalah nama dataset (`shop`, `sensors`).
    """
    server_url = os.environ.get(TEST_DATABASE_URL_ENV) or DEFAULT_DATABASE_URL
    suffix = uuid.uuid4().hex[:8]
    role = f"{DEMO_ROLE_PREFIX}{suffix}"
    password = uuid.uuid4().hex
    databases = {name: f"{TEST_DATABASE_PREFIX}demo_{name}_{suffix}" for name in DEMO_DATASET_NAMES}
    with psycopg.connect(server_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(password)
            )
        )
        connection.execute(
            sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(
                sql.Identifier(role)
            )
        )
    urls: dict[str, str] = {}
    try:
        for name, database in databases.items():
            _run_admin_statement(server_url, "CREATE DATABASE {}", database)
            _seed_demo_database(server_url, database, name, role)
            urls[name] = (
                make_url(server_url)
                .set(database=database, username=role, password=password)
                .render_as_string(hide_password=False)
            )
        yield urls
    finally:
        for database in databases.values():
            _run_admin_statement(server_url, "DROP DATABASE IF EXISTS {} WITH (FORCE)", database)
        with psycopg.connect(server_url, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


def _seed_demo_database(server_url: str, database: str, dataset: str, role: str) -> None:
    """Isi satu database demo dari `docker/demo/<dataset>.sql`, lalu beri hak baca ke `role`."""
    admin_url = make_url(server_url).set(database=database).render_as_string(hide_password=False)
    script = (DEMO_DIR / f"{dataset}.sql").read_text(encoding="utf-8")
    with psycopg.connect(admin_url, autocommit=True) as connection:
        # bytes: skrip dari file bukan LiteralString. Tanpa parameter, psycopg menjalankan
        # beberapa statement sekaligus.
        connection.execute(script.encode())
        role_id = sql.Identifier(role)
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        connection.execute(
            sql.SQL("REVOKE TEMPORARY ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database))
        )
        connection.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database), role_id)
        )
        connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role_id))
        connection.execute(
            sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(role_id)
        )
