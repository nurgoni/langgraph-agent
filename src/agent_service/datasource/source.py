"""`SqlDataSource`: satu database Postgres yang hanya dibaca (FR-51, ADR 0007).

Setiap query berjalan di transaksi `READ ONLY` dengan `statement_timeout` lokal. Koneksi di pool
diset read-only saat dibuat, jadi query yang lolos dari guard pun tidak bisa menulis. Pertahanan
utama tetap user database read-only di DSN.
"""

import logging
from collections.abc import Sequence
from typing import Final

import psycopg
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool, PoolTimeout

from agent_service.datasource.model import QueryFailedError, QueryResult

logger = logging.getLogger(__name__)

POOL_MIN_SIZE: Final = 0
POOL_MAX_SIZE: Final = 4
CONNECT_TIMEOUT_SECONDS: Final = 5
POOL_WAIT_TIMEOUT_SECONDS: Final = 10
MILLISECONDS_PER_SECOND: Final = 1000
TIMEOUT_SQL: Final = "SELECT set_config('statement_timeout', %s, true)"
CHECK_SQL: Final = "SELECT 1"
UNKNOWN_TYPE: Final = "unknown"

type QueryParams = Sequence[object]


async def _configure_connection(connection: AsyncConnection) -> None:
    """Setiap koneksi baru di pool hanya membuka transaksi read-only."""
    await connection.set_read_only(True)


class SqlDataSource:
    """Pool koneksi read-only ke satu database, beserta batas waktu query.

    Dibuat dan dibuka oleh `DataSourceRegistry` saat lifespan.
    """

    def __init__(self, data_source_id: str, database_url: str, timeout_seconds: int) -> None:
        """Inisialisasi data source tanpa membuka koneksi.

        Args:
            data_source_id: ID di registry, untuk log.
            database_url: DSN Postgres dengan user read-only.
            timeout_seconds: `statement_timeout` setiap query (`SQL_TIMEOUT_SECONDS`).
        """
        self._id = data_source_id
        self._timeout_seconds = timeout_seconds
        self._pool = AsyncConnectionPool(
            database_url,
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
            kwargs={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
            configure=_configure_connection,
            timeout=POOL_WAIT_TIMEOUT_SECONDS,
            open=False,
        )

    @property
    def timeout_seconds(self) -> int:
        """Batas waktu satu query, dalam detik."""
        return self._timeout_seconds

    async def open(self) -> None:
        """Buka pool dan pastikan database terjangkau.

        Raises:
            QueryFailedError: Jika database tidak bisa dihubungi.
        """
        await self._pool.open()
        await self.fetch(CHECK_SQL)

    async def close(self) -> None:
        """Tutup semua koneksi pool."""
        await self._pool.close()

    async def fetch(self, sql: str, params: QueryParams | None = None) -> QueryResult:
        """Jalankan satu query di transaksi read-only, lalu ambil semua barisnya.

        Args:
            sql: SQL yang sudah lolos `QueryGuard`, atau SQL internal inspector/profiler.
            params: Parameter `%s`, untuk nilai dari model (bukan identifier).

        Returns:
            Kolom, tipe Postgres, dan baris hasil.

        Raises:
            QueryFailedError: Error SQL, izin, timeout, atau database tidak terjangkau.
        """
        try:
            async with self._pool.connection() as connection, connection.transaction():
                cursor = connection.cursor()
                timeout_ms = str(self._timeout_seconds * MILLISECONDS_PER_SECOND)
                await cursor.execute(TIMEOUT_SQL, [timeout_ms])
                # bytes: SQL dari model bukan LiteralString, dan psycopg menerimanya apa adanya.
                await cursor.execute(sql.encode(), params)
                rows = await cursor.fetchall()
                return QueryResult(
                    columns=[column.name for column in cursor.description or []],
                    types=_type_names(connection, cursor.description or []),
                    rows=rows,
                )
        except psycopg.errors.QueryCanceled as error:
            raise QueryFailedError(
                f"The query was stopped after {self._timeout_seconds} seconds. "
                "Filter or aggregate more, or query fewer rows."
            ) from error
        except psycopg.Error as error:
            raise QueryFailedError(_database_message(error)) from error
        except PoolTimeout as error:
            logger.warning("Data source %s pool timed out", self._id)
            raise QueryFailedError("The database is not reachable right now.") from error


def _type_names(connection: AsyncConnection, description: Sequence[psycopg.Column]) -> list[str]:
    """Nama tipe Postgres setiap kolom hasil (`int4`, `timestamptz`, `numeric`, ...)."""
    names: list[str] = []
    for column in description:
        info = connection.adapters.types.get(column.type_code)
        names.append(UNKNOWN_TYPE if info is None else info.name)
    return names


def _database_message(error: psycopg.Error) -> str:
    """Pesan error database untuk model: pesan utama, tanpa DSN.

    >>> _database_message(psycopg.Error("boom"))
    'Database error: boom'
    """
    primary = error.diag.message_primary if error.diag is not None else None
    return f"Database error: {primary or str(error).strip()}"
