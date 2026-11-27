"""`SchemaInspector`: struktur database untuk eksplorasi (FR-51).

Semua informasi dibaca dari `pg_catalog`, terbatas pada tabel yang boleh dibaca user data source
(`has_table_privilege`). Nama tabel dari model selalu dicocokkan dulu ke katalog lewat `resolve`,
lalu di-quote, jadi identifier tidak pernah dirangkai mentah ke SQL.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from agent_service.datasource.model import QueryResult, TableNotFoundError, as_strings
from agent_service.datasource.source import SqlDataSource

DEFAULT_SCHEMA: Final = "public"
SEARCH_MAX_MATCHES: Final = 50
SAMPLE_ROWS: Final = 5
SUGGESTION_COUNT: Final = 5
QUOTE: Final = '"'

TABLES_SQL: Final = """
SELECT n.nspname, c.relname, obj_description(c.oid, 'pg_class'),
       CASE WHEN c.reltuples < 0 THEN NULL ELSE c.reltuples::bigint END
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'v', 'm', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg\\_%'
  AND has_table_privilege(c.oid, 'SELECT')
ORDER BY n.nspname, c.relname
"""

COLUMNS_SQL: Final = """
SELECT a.attname, format_type(a.atttypid, a.atttypmod), NOT a.attnotnull,
       col_description(a.attrelid, a.attnum), t.typcategory
FROM pg_attribute AS a
JOIN pg_type AS t ON t.oid = a.atttypid
WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY a.attnum
"""

# Kolom primary key, lalu foreign key keluar dan masuk: jalur join yang bisa dipakai model.
CONSTRAINTS_SQL: Final = """
SELECT con.contype,
       (SELECT n.nspname || '.' || c.relname FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace WHERE c.oid = con.conrelid),
       ARRAY(SELECT attname FROM pg_attribute
             WHERE attrelid = con.conrelid AND attnum = ANY (con.conkey) ORDER BY attnum),
       (SELECT n.nspname || '.' || c.relname FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace WHERE c.oid = con.confrelid),
       ARRAY(SELECT attname FROM pg_attribute
             WHERE attrelid = con.confrelid AND attnum = ANY (con.confkey) ORDER BY attnum)
FROM pg_constraint AS con
WHERE con.contype IN ('p', 'f')
  AND (con.conrelid = %s::regclass OR con.confrelid = %s::regclass)
ORDER BY con.contype DESC, con.conname
"""

SEARCH_SQL: Final = """
SELECT n.nspname, c.relname, NULL::text, obj_description(c.oid, 'pg_class')
FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'v', 'm', 'p') AND has_table_privilege(c.oid, 'SELECT')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND (c.relname ILIKE %s OR obj_description(c.oid, 'pg_class') ILIKE %s)
UNION ALL
SELECT n.nspname, c.relname, a.attname, col_description(c.oid, a.attnum)
FROM pg_attribute AS a
JOIN pg_class AS c ON c.oid = a.attrelid
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'v', 'm', 'p') AND has_table_privilege(c.oid, 'SELECT')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND a.attnum > 0 AND NOT a.attisdropped
  AND (a.attname ILIKE %s OR col_description(c.oid, a.attnum) ILIKE %s)
ORDER BY 1, 2, 3 NULLS FIRST
LIMIT %s
"""


@dataclass(frozen=True)
class TableRef:
    """Tabel yang sudah dicocokkan ke katalog database.

    >>> TableRef("public", "orders").qualified
    'public.orders'
    >>> TableRef("public", 'we"ird').quoted
    '"public"."we""ird"'
    """

    schema: str
    name: str

    @property
    def qualified(self) -> str:
        """Nama `schema.table` untuk ditampilkan dan dipakai `regclass`."""
        return f"{self.schema}.{self.name}"

    @property
    def quoted(self) -> str:
        """Nama yang aman dirangkai ke SQL."""
        return f"{quote_identifier(self.schema)}.{quote_identifier(self.name)}"


@dataclass(frozen=True)
class TableInfo:
    """Satu tabel atau view yang bisa dibaca."""

    ref: TableRef
    comment: str | None
    estimated_rows: int | None


@dataclass(frozen=True)
class ColumnInfo:
    """Satu kolom: tipe, nullable, komentar, dan kategori tipe Postgres (`typcategory`)."""

    name: str
    type: str
    nullable: bool
    comment: str | None
    category: str


@dataclass(frozen=True)
class Relation:
    """Primary key (`target` kosong) atau foreign key `table(columns) → target(target_columns)`."""

    kind: str
    table: str
    columns: tuple[str, ...]
    target: str | None = None
    target_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class TableDescription:
    """Isi `describe_table`: kolom, relasi, perkiraan jumlah baris, dan contoh baris."""

    table: TableInfo
    columns: Sequence[ColumnInfo]
    relations: Sequence[Relation]
    sample: QueryResult


@dataclass(frozen=True)
class SchemaMatch:
    """Hasil `search_schema`: tabel (`column` kosong) atau kolom yang cocok dengan kata kunci."""

    table: str
    column: str | None
    comment: str | None


def quote_identifier(name: str) -> str:
    """Quote identifier Postgres.

    >>> quote_identifier("order")
    '"order"'
    """
    return QUOTE + name.replace(QUOTE, QUOTE * 2) + QUOTE


class SchemaInspector:
    """Membaca struktur satu data source."""

    def __init__(self, source: SqlDataSource) -> None:
        """Inisialisasi inspector.

        Args:
            source: Data source read-only yang sudah dibuka.
        """
        self._source = source

    async def tables(self) -> list[TableInfo]:
        """Semua tabel dan view yang bisa dibaca, urut schema lalu nama."""
        result = await self._source.fetch(TABLES_SQL)
        tables: list[TableInfo] = []
        for schema, name, comment, estimate in result.rows:
            ref = TableRef(str(schema), str(name))
            tables.append(TableInfo(ref, _text(comment), _int(estimate)))
        return tables

    async def resolve(self, table: str) -> TableInfo:
        """Cocokkan `table` atau `schema.table` dari model ke tabel yang ada.

        Raises:
            TableNotFoundError: Tabel tidak ada atau tidak boleh dibaca, dengan saran nama.
        """
        schema, _, name = table.strip().rpartition(".")
        wanted = TableRef(schema or DEFAULT_SCHEMA, name)
        available = await self.tables()
        for info in available:
            if info.ref.schema == wanted.schema and info.ref.name.lower() == name.lower():
                return info
        raise TableNotFoundError(_not_found_message(table, available))

    async def columns(self, table: TableInfo) -> list[ColumnInfo]:
        """Kolom tabel, urut posisi."""
        result = await self._source.fetch(COLUMNS_SQL, [table.ref.quoted])
        columns: list[ColumnInfo] = []
        for name, type_name, nullable, comment, category in result.rows:
            columns.append(
                ColumnInfo(str(name), str(type_name), bool(nullable), _text(comment), str(category))
            )
        return columns

    async def describe(self, table: str) -> TableDescription:
        """Kolom, primary/foreign key, perkiraan baris, dan beberapa contoh baris tabel.

        Raises:
            TableNotFoundError: Tabel tidak ada atau tidak boleh dibaca.
        """
        info = await self.resolve(table)
        relations = await self._relations(info)
        sample = await self._source.fetch(f"SELECT * FROM {info.ref.quoted} LIMIT {SAMPLE_ROWS}")
        return TableDescription(info, await self.columns(info), relations, sample)

    async def search(self, keyword: str) -> list[SchemaMatch]:
        """Tabel dan kolom yang nama atau komentarnya memuat `keyword` (tidak peka huruf besar)."""
        pattern = f"%{_escape_like(keyword.strip())}%"
        result = await self._source.fetch(
            SEARCH_SQL, [pattern, pattern, pattern, pattern, SEARCH_MAX_MATCHES]
        )
        matches: list[SchemaMatch] = []
        for schema, table, column, comment in result.rows:
            matches.append(SchemaMatch(f"{schema}.{table}", _text(column), _text(comment)))
        return matches

    async def _relations(self, info: TableInfo) -> list[Relation]:
        """Primary key tabel dan foreign key yang keluar dari atau masuk ke tabel ini."""
        quoted = info.ref.quoted
        result = await self._source.fetch(CONSTRAINTS_SQL, [quoted, quoted])
        relations: list[Relation] = []
        for kind, table, columns, target, target_columns in result.rows:
            is_primary = kind == "p"
            relations.append(
                Relation(
                    kind="primary key" if is_primary else "foreign key",
                    table=str(table),
                    columns=as_strings(columns),
                    target=None if is_primary else str(target),
                    target_columns=() if is_primary else as_strings(target_columns),
                )
            )
        return relations


def _not_found_message(table: str, available: Sequence[TableInfo]) -> str:
    """Pesan tabel tidak ditemukan, dengan beberapa nama tabel yang mirip atau tersedia."""
    needle = table.rpartition(".")[2].lower()
    similar = [info.ref.qualified for info in available if needle[:3] in info.ref.name.lower()]
    suggestions = similar or [info.ref.qualified for info in available]
    listing = ", ".join(suggestions[:SUGGESTION_COUNT]) or "none"
    return f"Table {table!r} was not found. Available tables include: {listing}."


def _escape_like(text: str) -> str:
    """Escape wildcard `LIKE`, supaya kata kunci dicocokkan apa adanya.

    >>> _escape_like("50%_off")
    '50\\\\%\\\\_off'
    """
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _text(value: object) -> str | None:
    """Teks dari kolom katalog yang bisa NULL."""
    return None if value is None else str(value)


def _int(value: object) -> int | None:
    """Bilangan bulat dari kolom katalog yang bisa NULL."""
    return value if isinstance(value, int) else None
