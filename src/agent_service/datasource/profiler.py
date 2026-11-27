"""`TableProfiler`: statistik kolom untuk `profile_table` (FR-51, keputusan user F39).

Tabel dengan perkiraan baris sampai `PROFILE_EXACT_MAX_ROWS` diprofil exact. Tabel yang lebih besar
diprofil dari `TABLESAMPLE SYSTEM` dengan ukuran sampel sekitar batas itu, dan hasilnya ditandai
`sampled`, supaya model tahu angkanya perkiraan. Statistik per kolom bergantung pada kategori tipe
Postgres (`typcategory`): angka dan tanggal mendapat min/max, teks dan boolean mendapat nilai
teratas, dan tipe lain (JSON, array) hanya jumlah null.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from agent_service.datasource.inspector import ColumnInfo, SchemaInspector, quote_identifier
from agent_service.datasource.model import TableNotFoundError, as_int
from agent_service.datasource.source import SqlDataSource

NUMERIC_CATEGORY: Final = "N"
DATETIME_CATEGORY: Final = "D"
STRING_CATEGORY: Final = "S"
BOOLEAN_CATEGORY: Final = "B"
ORDERED_CATEGORIES: Final = frozenset({NUMERIC_CATEGORY, DATETIME_CATEGORY, STRING_CATEGORY})
TOP_VALUE_CATEGORIES: Final = frozenset({STRING_CATEGORY, BOOLEAN_CATEGORY})
DISTINCT_CATEGORIES: Final = ORDERED_CATEGORIES | {BOOLEAN_CATEGORY}
TOP_VALUES: Final = 5
MAX_PROFILE_COLUMNS: Final = 30
PERCENT: Final = 100.0
# Sampel minimal 0,01% supaya tabel sangat besar tetap menghasilkan baris.
MIN_SAMPLE_PERCENT: Final = 0.01


@dataclass(frozen=True)
class ColumnProfile:
    """Statistik satu kolom. Nilai `None` berarti tidak dihitung untuk tipe kolom ini."""

    column: ColumnInfo
    null_fraction: float
    distinct_count: int | None
    minimum: object | None
    maximum: object | None
    top_values: Sequence[tuple[object, int]]


@dataclass(frozen=True)
class TableProfile:
    """Hasil `profile_table`: jumlah baris yang diprofil, apakah dari sampel, dan profil kolom."""

    table: str
    rows_profiled: int
    sampled: bool
    sample_percent: float | None
    columns: Sequence[ColumnProfile]
    skipped_columns: Sequence[str]


class TableProfiler:
    """Menghitung statistik kolom satu tabel."""

    def __init__(
        self, source: SqlDataSource, inspector: SchemaInspector, exact_max_rows: int
    ) -> None:
        """Inisialisasi profiler.

        Args:
            source: Data source read-only yang sudah dibuka.
            inspector: Inspector data source yang sama, untuk mencocokkan tabel dan kolom.
            exact_max_rows: Batas perkiraan baris untuk profil exact (`PROFILE_EXACT_MAX_ROWS`).
        """
        self._source = source
        self._inspector = inspector
        self._exact_max_rows = exact_max_rows

    async def profile(self, table: str, columns: Sequence[str] | None = None) -> TableProfile:
        """Profil kolom `columns` (default: semua, maksimal `MAX_PROFILE_COLUMNS`) dari `table`.

        Raises:
            TableNotFoundError: Tabel atau salah satu kolom tidak ada.
            QueryFailedError: Query statistik gagal, misalnya karena timeout.
        """
        info = await self._inspector.resolve(table)
        selected = _select_columns(await self._inspector.columns(info), columns, table)
        sample_percent = sample_percent_for(info.estimated_rows, self._exact_max_rows)
        source_sql = info.ref.quoted
        if sample_percent is not None:
            source_sql = f"{source_sql} TABLESAMPLE SYSTEM ({sample_percent:.4f})"
        profiled = selected[:MAX_PROFILE_COLUMNS]
        rows, profiles = await self._summaries(source_sql, profiled)
        return TableProfile(
            table=info.ref.qualified,
            rows_profiled=rows,
            sampled=sample_percent is not None,
            sample_percent=sample_percent,
            columns=profiles,
            skipped_columns=[column.name for column in selected[MAX_PROFILE_COLUMNS:]],
        )

    async def _summaries(
        self, source_sql: str, columns: Sequence[ColumnInfo]
    ) -> tuple[int, list[ColumnProfile]]:
        """Satu query untuk jumlah baris, null, distinct, min, dan max semua kolom."""
        expressions = ["count(*)"]
        for column in columns:
            expressions.extend(_aggregates(column))
        result = await self._source.fetch(f"SELECT {', '.join(expressions)} FROM {source_sql}")
        values = list(result.rows[0])
        total = as_int(values.pop(0))
        profiles: list[ColumnProfile] = []
        for column in columns:
            non_null, distinct, minimum, maximum = (values.pop(0) for _ in range(4))
            top_values = await self._top_values(source_sql, column)
            profiles.append(
                ColumnProfile(
                    column=column,
                    null_fraction=0.0 if total == 0 else 1 - as_int(non_null) / total,
                    distinct_count=None if distinct is None else as_int(distinct),
                    minimum=minimum,
                    maximum=maximum,
                    top_values=top_values,
                )
            )
        return total, profiles

    async def _top_values(self, source_sql: str, column: ColumnInfo) -> list[tuple[object, int]]:
        """Nilai paling sering untuk kolom teks dan boolean."""
        if column.category not in TOP_VALUE_CATEGORIES:
            return []
        name = quote_identifier(column.name)
        result = await self._source.fetch(
            f"SELECT {name}, count(*) FROM {source_sql} WHERE {name} IS NOT NULL "
            f"GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {TOP_VALUES}"
        )
        return [(value, as_int(count)) for value, count in result.rows]


def sample_percent_for(estimated_rows: int | None, exact_max_rows: int) -> float | None:
    """Persentase `TABLESAMPLE` agar sampel sekitar `exact_max_rows` baris, atau `None` (exact).

    >>> sample_percent_for(500, 1000) is None, sample_percent_for(None, 1000) is None
    (True, True)
    >>> sample_percent_for(4000, 1000)
    25.0
    """
    if estimated_rows is None or estimated_rows <= exact_max_rows:
        return None
    return max(MIN_SAMPLE_PERCENT, PERCENT * exact_max_rows / estimated_rows)


def _aggregates(column: ColumnInfo) -> list[str]:
    """Empat ekspresi agregat kolom: non-null, distinct, min, max (`NULL` jika tidak relevan).

    >>> _aggregates(ColumnInfo("payload", "jsonb", True, None, "U"))
    ['count("payload")', 'NULL', 'NULL', 'NULL']
    """
    name = quote_identifier(column.name)
    distinct = f"count(DISTINCT {name})" if column.category in DISTINCT_CATEGORIES else "NULL"
    if column.category not in ORDERED_CATEGORIES:
        return [f"count({name})", distinct, "NULL", "NULL"]
    return [f"count({name})", distinct, f"min({name})", f"max({name})"]


def _select_columns(
    available: Sequence[ColumnInfo], wanted: Sequence[str] | None, table: str
) -> list[ColumnInfo]:
    """Kolom yang diminta, urut sesuai permintaan, atau semua kolom tabel.

    Raises:
        TableNotFoundError: Ada kolom yang tidak dimiliki tabel.
    """
    if not wanted:
        return list(available)
    by_name = {column.name.lower(): column for column in available}
    missing = [name for name in wanted if name.lower() not in by_name]
    if missing:
        listing = ", ".join(column.name for column in available)
        raise TableNotFoundError(
            f"Columns {missing} are not in {table}. Its columns are: {listing}."
        )
    return [by_name[name.lower()] for name in wanted]
