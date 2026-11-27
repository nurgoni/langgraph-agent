"""`QueryGuard`: hanya satu `SELECT` read-only, dengan `LIMIT` yang dipaksa (FR-51, ADR 0007).

Guard adalah lapisan kedua. Pertahanan utama tetap user database read-only dan transaksi
`READ ONLY` di `SqlDataSource`; guard memberi pesan yang jelas ke model sebelum query sampai ke
database, dan membatasi jumlah baris. Daftar fungsi terlarang bukan daftar lengkap, karena fungsi
yang menulis tetap ditolak transaksi read-only.
"""

from dataclasses import dataclass
from typing import Final

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from agent_service.datasource.model import QueryRejectedError

SQL_DIALECT: Final = "postgres"
RESULT_ALIAS: Final = "result"
# Node yang tidak boleh muncul di mana pun dalam query, termasuk di dalam CTE.
FORBIDDEN_NODES: Final = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Command,
    exp.Copy,
    exp.Into,
    exp.Lock,
)
# Fungsi yang mengubah state server, membaca file, atau membuka koneksi keluar.
FORBIDDEN_FUNCTION_PREFIXES: Final = ("pg_", "lo_", "dblink")
FORBIDDEN_FUNCTIONS: Final = frozenset({"nextval", "setval", "set_config", "query_to_xml"})


@dataclass(frozen=True)
class GuardedQuery:
    """Query yang lolos guard: SQL final dengan `LIMIT max_rows + 1` untuk mendeteksi pemotongan."""

    sql: str
    max_rows: int


class QueryGuard:
    """Memeriksa SQL dari model dan membungkusnya dengan batas baris.

    >>> guard = QueryGuard(max_rows=100)
    >>> guard.check("SELECT region, count(*) FROM orders GROUP BY 1").sql
    'SELECT * FROM (SELECT region, COUNT(*) FROM orders GROUP BY 1) AS result LIMIT 101'
    >>> guard.check("DELETE FROM orders")
    Traceback (most recent call last):
    agent_service.datasource.model.QueryRejectedError: Only SELECT queries are allowed.
    """

    def __init__(self, max_rows: int) -> None:
        """Inisialisasi guard.

        Args:
            max_rows: Batas baris hasil (`SQL_MAX_ROWS`).
        """
        self._max_rows = max_rows

    def check(self, sql: str) -> GuardedQuery:
        """Periksa `sql`, lalu kembalikan versi yang dibatasi `LIMIT`.

        Raises:
            QueryRejectedError: Bukan tepat satu query `SELECT`, mengandung perintah yang
                menulis, `SELECT INTO`, `FOR UPDATE`, atau fungsi terlarang.
        """
        query = self._single_query(sql)
        self._reject_forbidden_nodes(query)
        self._reject_forbidden_functions(query)
        limited = exp.select("*").from_(query.subquery(RESULT_ALIAS)).limit(self._max_rows + 1)
        return GuardedQuery(limited.sql(dialect=SQL_DIALECT), self._max_rows)

    def _single_query(self, sql: str) -> exp.Query:
        """Parse `sql` dan pastikan isinya tepat satu query (`SELECT`, `UNION`, dan sejenisnya)."""
        try:
            statements = [item for item in sqlglot.parse(sql, dialect=SQL_DIALECT) if item]
        except ParseError as error:
            raise QueryRejectedError(f"The SQL could not be parsed: {error}") from error
        if len(statements) != 1:
            raise QueryRejectedError("Send exactly one SQL statement.")
        statement = statements[0]
        if not isinstance(statement, exp.Query):
            raise QueryRejectedError("Only SELECT queries are allowed.")
        return statement

    def _reject_forbidden_nodes(self, query: exp.Query) -> None:
        """Tolak perintah yang menulis, `SELECT INTO`, dan `FOR UPDATE`, juga di dalam CTE."""
        for node in query.walk():
            if isinstance(node, FORBIDDEN_NODES):
                raise QueryRejectedError(
                    "Only read-only SELECT queries are allowed (no writes, INTO, or locks)."
                )

    def _reject_forbidden_functions(self, query: exp.Query) -> None:
        """Tolak fungsi administrasi server dan fungsi yang mengubah state."""
        for function in query.find_all(exp.Anonymous):
            name = function.name.lower()
            if name in FORBIDDEN_FUNCTIONS or name.startswith(FORBIDDEN_FUNCTION_PREFIXES):
                raise QueryRejectedError(f"The function {name}() is not allowed.")


if __name__ == "__main__":
    print(QueryGuard(max_rows=10).check("SELECT 1 AS one").sql)
