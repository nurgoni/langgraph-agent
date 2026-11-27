"""`SqlDataSource` dan user database read-only, langsung ke database demo (FR-51).

Acceptance F39: user read-only tetap tidak bisa menulis walaupun guard dilewati, dan query lambat
berhenti karena timeout.
"""

from collections.abc import AsyncIterator

import psycopg
import pytest

from agent_service.datasource.model import QueryFailedError
from agent_service.datasource.source import SqlDataSource

TIMEOUT_SECONDS = 1


@pytest.fixture
async def shop(demo_database_urls: dict[str, str]) -> AsyncIterator[SqlDataSource]:
    source = SqlDataSource("shop", demo_database_urls["shop"], TIMEOUT_SECONDS)
    await source.open()
    yield source
    await source.close()


async def test_fetch_returns_columns_postgres_types_and_rows(shop: SqlDataSource) -> None:
    result = await shop.fetch(
        "SELECT customer_id, signup_date FROM customers WHERE customer_id = %s", [1]
    )

    assert list(result.columns) == ["customer_id", "signup_date"]
    assert list(result.types) == ["int4", "date"]
    assert len(result.rows) == 1


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO products VALUES (999, 'x', 'y', 1)",
        "DELETE FROM refunds",
        "CREATE TABLE stolen (a int)",
        "CREATE TEMP TABLE scratch (a int)",
    ],
)
async def test_writes_fail_even_when_the_guard_is_bypassed(shop: SqlDataSource, sql: str) -> None:
    with pytest.raises(QueryFailedError, match="Database error"):
        await shop.fetch(sql)


def test_read_only_user_cannot_write_on_a_raw_connection(
    demo_database_urls: dict[str, str],
) -> None:
    """Pertahanan utama: tanpa transaksi read-only dari service pun, user ini tidak bisa menulis."""
    with psycopg.connect(demo_database_urls["shop"], autocommit=True) as connection:
        for statement in (
            "BEGIN READ WRITE; DELETE FROM refunds; COMMIT",
            "BEGIN READ WRITE; UPDATE customers SET region = 'x'; COMMIT",
            "BEGIN READ WRITE; CREATE TABLE stolen (a int); COMMIT",
            "BEGIN READ WRITE; CREATE TEMP TABLE scratch (a int); COMMIT",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(statement.encode())
            connection.execute("ROLLBACK")


async def test_slow_query_is_stopped_by_the_statement_timeout(shop: SqlDataSource) -> None:
    with pytest.raises(QueryFailedError, match=f"stopped after {TIMEOUT_SECONDS} seconds"):
        await shop.fetch("SELECT pg_sleep(5)")


async def test_sql_errors_are_reported_without_the_dsn(
    shop: SqlDataSource, demo_database_urls: dict[str, str]
) -> None:
    with pytest.raises(QueryFailedError) as caught:
        await shop.fetch("SELECT missing_column FROM orders")

    assert "missing_column" in str(caught.value)
    assert demo_database_urls["shop"] not in str(caught.value)


async def test_connections_are_read_only_even_for_a_user_that_may_write(database_url: str) -> None:
    """Lapisan kedua: transaksi read-only berlaku walaupun DSN memakai user dengan hak tulis."""
    source = SqlDataSource("owner", database_url, TIMEOUT_SECONDS)
    await source.open()
    try:
        with pytest.raises(QueryFailedError, match="read-only transaction"):
            await source.fetch("CREATE TABLE should_not_exist (a int)")
    finally:
        await source.close()
