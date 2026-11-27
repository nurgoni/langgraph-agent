"""`QueryGuard` (FR-51): hanya satu `SELECT` read-only, dengan `LIMIT` dipaksa.

Acceptance F39: `INSERT`, `DROP`, multi-statement, dan fungsi yang menulis ditolak.
"""

import pytest

from agent_service.datasource.guard import QueryGuard
from agent_service.datasource.model import QueryRejectedError

MAX_ROWS = 100


@pytest.fixture
def guard() -> QueryGuard:
    return QueryGuard(max_rows=MAX_ROWS)


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("INSERT INTO orders VALUES (1)", "Only SELECT"),
        ("UPDATE orders SET status = 'x'", "Only SELECT"),
        ("DELETE FROM orders", "Only SELECT"),
        ("DROP TABLE orders", "Only SELECT"),
        ("TRUNCATE orders", "Only SELECT"),
        ("CREATE TABLE t (a int)", "Only SELECT"),
        ("ALTER TABLE orders ADD COLUMN x int", "Only SELECT"),
        ("COPY orders TO '/tmp/x'", "Only SELECT"),
        ("CALL refresh()", "Only SELECT"),
        ("SELECT 1; DROP TABLE orders", "exactly one"),
        ("SELECT 1 -- note\n; SELECT 2", "exactly one"),
        ("WITH gone AS (DELETE FROM orders RETURNING *) SELECT * FROM gone", "read-only"),
        ("SELECT * INTO copy_of_orders FROM orders", "read-only"),
        ("SELECT * FROM orders FOR UPDATE", "read-only"),
        ("SELECT pg_sleep(60)", "pg_sleep"),
        ("SELECT pg_terminate_backend(1)", "pg_terminate_backend"),
        ("SELECT nextval('orders_seq')", "nextval"),
        ("SELECT set_config('role', 'admin', false)", "set_config"),
        ("SELECT lo_import('/etc/passwd')", "lo_import"),
        ("SELECT dblink_exec('host=x', 'DROP TABLE t')", "dblink_exec"),
        ("SELEC * FROM", "could not be parsed"),
        ("", "exactly one"),
    ],
)
def test_writes_multi_statements_and_unsafe_functions_are_rejected(
    guard: QueryGuard, sql: str, message: str
) -> None:
    with pytest.raises(QueryRejectedError, match=message):
        guard.check(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "select region, count(*) from orders group by region",
        "WITH m AS (SELECT date_trunc('month', ordered_at) AS month FROM orders) SELECT * FROM m",
        "SELECT a FROM t UNION ALL SELECT b FROM u",
        "SELECT * FROM orders ORDER BY ordered_at DESC LIMIT 5",
        "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY value) FROM readings",
    ],
)
def test_read_only_queries_pass_with_an_outer_limit(guard: QueryGuard, sql: str) -> None:
    guarded = guard.check(sql)

    assert guarded.sql.endswith(f"LIMIT {MAX_ROWS + 1}")
    assert guarded.sql.startswith("SELECT * FROM (")
    assert guarded.max_rows == MAX_ROWS
