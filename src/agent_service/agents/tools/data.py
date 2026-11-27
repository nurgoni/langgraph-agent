"""Tool eksplorasi data generik (FR-51, F39): `list_data_sources`, `search_schema`,
`describe_table`, `profile_table`, dan `run_sql`.

Tool hanya bisa memakai data source yang aktif di project run ini
(`configurable["project_data_source_ids"]`), dan di-bind ke model hanya pada giliran yang
project-nya punya data source (keputusan user F39, pola skill F28). Tidak ada nama domain di tool
atau deskripsinya (NFR-13): pengetahuan data datang dari database dan katalog (F48).

Hasil `run_sql` disimpan sebagai Parquet di workspace thread (`data/<name>.parquet`), dan model
menerima pratinjau. Kode di sandbox memuat file itu; sandbox tidak pernah memegang kredensial
database (ADR 0007).
"""

import asyncio
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import date, datetime
from typing import Any, Final

from langchain_core.tools import BaseTool, ToolException, tool
from langgraph.prebuilt import ToolRuntime

from agent_service.core.constants import PROJECT_DATA_SOURCE_IDS_CONFIG_KEY
from agent_service.datasource.guard import QueryGuard
from agent_service.datasource.inspector import (
    Relation,
    SchemaInspector,
    SchemaMatch,
    TableDescription,
)
from agent_service.datasource.model import (
    DataSourceError,
    DataSourceNotFoundError,
    DataSourceStatus,
    QueryResult,
)
from agent_service.datasource.profiler import TableProfile, TableProfiler
from agent_service.datasource.registry import DataSourceRegistry
from agent_service.datasource.results import to_parquet
from agent_service.datasource.source import SqlDataSource
from agent_service.files.workspace import WorkspaceFileTooLargeError
from agent_service.harness.runtime import HarnessContext
from agent_service.harness.tools.files import CONFIGURABLE_KEY, workspace_scope

LIST_DATA_SOURCES_TOOL_NAME: Final = "list_data_sources"
SEARCH_SCHEMA_TOOL_NAME: Final = "search_schema"
DESCRIBE_TABLE_TOOL_NAME: Final = "describe_table"
PROFILE_TABLE_TOOL_NAME: Final = "profile_table"
RUN_SQL_TOOL_NAME: Final = "run_sql"

RESULTS_FOLDER: Final = "data"
RESULT_EXTENSION: Final = ".parquet"
DEFAULT_RESULT_NAME: Final = "query"
RESULT_NAME_MAX_CHARS: Final = 60
UNSAFE_NAME_CHARS: Final = re.compile(r"[^a-z0-9_-]+")
PREVIEW_ROWS: Final = 20
CELL_MAX_CHARS: Final = 60
NULL_TEXT: Final = "NULL"
FLOAT_FORMAT: Final = ".6g"
ELLIPSIS: Final = "..."

NO_DATA_SOURCES_TEXT: Final = "No data sources are active in this project."
CHOOSE_DATA_SOURCE_TEMPLATE: Final = (
    "This project has several data sources ({ids}). Pass data_source with one of them."
)
NO_MATCHES_TEMPLATE: Final = "No tables or columns match {keyword!r}."
SAMPLED_NOTE_TEMPLATE: Final = (
    "Profiled a random sample of about {percent:.2f}% of the table ({rows} rows), so counts are "
    "estimates and rare values (outliers, single bad rows) may be missing. Use run_sql for exact "
    "checks."
)


def project_data_source_ids(config: Mapping[str, Any] | None) -> list[str]:  # Any: RunnableConfig
    """ID data source aktif dari `configurable`, atau daftar kosong di luar project.

    >>> project_data_source_ids({"configurable": {"project_data_source_ids": ["shop"]}})
    ['shop']
    >>> project_data_source_ids(None)
    []
    """
    configurable = (config or {}).get(CONFIGURABLE_KEY) or {}
    value = configurable.get(PROJECT_DATA_SOURCE_IDS_CONFIG_KEY)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def result_path(name: str) -> str:
    """Path workspace hasil `run_sql` dari nama pilihan model.

    >>> result_path("Monthly Totals (2026)")
    'data/monthly_totals_2026.parquet'
    >>> result_path("../")
    'data/query.parquet'
    """
    slug = UNSAFE_NAME_CHARS.sub("_", name.strip().lower()).strip("_-")[:RESULT_NAME_MAX_CHARS]
    return f"{RESULTS_FOLDER}/{slug or DEFAULT_RESULT_NAME}{RESULT_EXTENSION}"


class DataAccess:
    """Data source yang boleh dipakai tool di satu run, beserta guard dan batas profil.

    Class karena menyimpan registry dan batas dari `Settings`, dan dipakai semua tool data.
    """

    def __init__(
        self, registry: DataSourceRegistry, max_rows: int, profile_exact_max_rows: int
    ) -> None:
        """Inisialisasi akses.

        Args:
            registry: Registry yang dibuka di lifespan.
            max_rows: Batas baris `run_sql` (`SQL_MAX_ROWS`).
            profile_exact_max_rows: Batas profil exact (`PROFILE_EXACT_MAX_ROWS`).
        """
        self._registry = registry
        self._guard = QueryGuard(max_rows)
        self._profile_exact_max_rows = profile_exact_max_rows

    @property
    def guard(self) -> QueryGuard:
        """Guard `run_sql`."""
        return self._guard

    def has_data_sources(self, config: Mapping[str, Any] | None) -> bool:  # Any: RunnableConfig
        """Cek apakah project run ini punya data source terdaftar."""
        return bool(self.statuses(config))

    def statuses(self, config: Mapping[str, Any] | None) -> list[DataSourceStatus]:  # Any: config
        """Status data source project run ini, urut sesuai registry."""
        return self._registry.statuses(project_data_source_ids(config))

    # Any: RunnableConfig LangGraph berupa dict bebas.
    def source(self, config: Mapping[str, Any] | None, requested: str) -> SqlDataSource:
        """Data source `requested`, atau satu-satunya data source project jika kosong.

        Raises:
            DataSourceNotFoundError: Tidak aktif di project ini, atau tidak terdaftar.
            DataSourceUnavailableError: Terdaftar tapi tidak bisa dipakai.
            DataSourceError: `requested` kosong padahal project punya beberapa data source.
        """
        allowed = [status.id for status in self.statuses(config)]
        if not requested.strip():
            if not allowed:
                raise DataSourceError(NO_DATA_SOURCES_TEXT)
            if len(allowed) > 1:
                raise DataSourceError(CHOOSE_DATA_SOURCE_TEMPLATE.format(ids=", ".join(allowed)))
            requested = allowed[0]
        if requested.strip() not in allowed:
            raise DataSourceNotFoundError(requested.strip())
        return self._registry.get(requested.strip())

    def profiler(self, source: SqlDataSource) -> TableProfiler:
        """Profiler untuk `source` dengan batas profil exact dari `Settings`."""
        return TableProfiler(source, SchemaInspector(source), self._profile_exact_max_rows)


def create_data_tools(access: DataAccess) -> list[BaseTool]:
    """Buat lima tool data yang memakai `access`.

    Function, bukan class: factory `@tool` (AGENTS.md § Class vs Function).
    """

    @tool(LIST_DATA_SOURCES_TOOL_NAME)
    async def list_data_sources(runtime: ToolRuntime[HarnessContext]) -> str:
        """List the databases you can query in this conversation, with what each contains.

        Call this first when a question needs data. Then use search_schema or describe_table to
        find the right tables before writing SQL.
        """
        return render_sources(access.statuses(runtime.config))

    @tool(SEARCH_SCHEMA_TOOL_NAME)
    async def search_schema(
        keyword: str, runtime: ToolRuntime[HarnessContext], data_source: str = ""
    ) -> str:
        """Find tables and columns whose name or description contains a keyword.

        Args:
            keyword: A word to look for, such as a business term or part of a column name.
            data_source: Data source id from list_data_sources. Optional if there is only one.
        """

        async def search() -> str:
            source = access.source(runtime.config, data_source)
            return render_matches(keyword, await SchemaInspector(source).search(keyword))

        return await _for_model(search)

    @tool(DESCRIBE_TABLE_TOOL_NAME)
    async def describe_table(
        table: str, runtime: ToolRuntime[HarnessContext], data_source: str = ""
    ) -> str:
        """Show a table's columns, types, descriptions, keys and join paths, size, and sample rows.

        Args:
            table: Table name, optionally as schema.table.
            data_source: Data source id from list_data_sources. Optional if there is only one.
        """

        async def describe() -> str:
            source = access.source(runtime.config, data_source)
            return render_description(await SchemaInspector(source).describe(table))

        return await _for_model(describe)

    @tool(PROFILE_TABLE_TOOL_NAME)
    async def profile_table(
        table: str,
        runtime: ToolRuntime[HarnessContext],
        columns: list[str] | None = None,
        data_source: str = "",
    ) -> str:
        """Profile columns of a table: share of nulls, distinct values, min and max, most common
        values. Use it to check data quality and value ranges before analysing.

        Args:
            table: Table name, optionally as schema.table.
            columns: Columns to profile. Leave empty to profile every column.
            data_source: Data source id from list_data_sources. Optional if there is only one.
        """

        async def profile() -> str:
            source = access.source(runtime.config, data_source)
            return render_profile(await access.profiler(source).profile(table, columns))

        return await _for_model(profile)

    @tool(RUN_SQL_TOOL_NAME)
    async def run_sql(
        sql: str, name: str, runtime: ToolRuntime[HarnessContext], data_source: str = ""
    ) -> str:
        """Run one read-only SELECT query (PostgreSQL) and save the full result to the workspace.

        You get a preview of the first rows and the path of a Parquet file with every row, which
        code can load (for example pandas.read_parquet). Aggregate in SQL when you can. Only a
        single SELECT is allowed; results are capped at a maximum number of rows.

        Args:
            sql: One SELECT statement. Do not end it with a semicolon followed by more SQL.
            name: Short name for the result file, such as "monthly_totals".
            data_source: Data source id from list_data_sources. Optional if there is only one.
        """

        async def query() -> str:
            scope = workspace_scope(runtime)
            source = access.source(runtime.config, data_source)
            guarded = access.guard.check(sql)
            result = await source.fetch(guarded.sql)
            truncated = len(result.rows) > guarded.max_rows
            kept = QueryResult(result.columns, result.types, result.rows[: guarded.max_rows])
            path = result_path(name)
            content = await asyncio.to_thread(to_parquet, kept)
            try:
                await scope.context.workspace.write(scope.thread_id, path, content)
            except WorkspaceFileTooLargeError as error:
                raise ToolException(f"{error}. Select fewer rows or columns.") from error
            return render_query_result(kept, path, truncated, guarded.max_rows)

        return await _for_model(query)

    return [list_data_sources, search_schema, describe_table, profile_table, run_sql]


async def _for_model(action: Callable[[], Awaitable[str]]) -> str:
    """Jalankan aksi tool. Error data source dikembalikan ke model sebagai `ToolException`."""
    try:
        return await action()
    except DataSourceError as error:
        raise ToolException(str(error)) from error


class DataToolkit:
    """Tool data untuk agent: semua tool didaftarkan, dan di-bind hanya jika project punya data.

    Class karena menyimpan tool yang dibuat sekali, dan dipakai `ToolCallingAgent` seperti
    `SkillToolkit` (`tools` dan `tools_for`).
    """

    def __init__(self, access: DataAccess) -> None:
        """Inisialisasi toolkit.

        Args:
            access: Akses data source untuk semua run agent ini.
        """
        self._access = access
        self._tools = create_data_tools(access)

    @property
    def tools(self) -> list[BaseTool]:
        """Semua tool data, untuk didaftarkan di `ToolNode` saat compile."""
        return list(self._tools)

    def tools_for(self, config: Mapping[str, Any] | None) -> list[BaseTool]:  # Any: config
        """Tool yang di-bind ke model pada giliran ini: semua tool data, atau tidak sama sekali."""
        return self.tools if self._access.has_data_sources(config) else []


def render_sources(statuses: Sequence[DataSourceStatus]) -> str:
    """Daftar data source project untuk model.

    >>> print(render_sources([DataSourceStatus("a", "Sales data", True),
    ...                       DataSourceStatus("b", "Logs", False, "Cannot connect.")]))
    - a: Sales data
    - b (unavailable: Cannot connect.): Logs
    """
    if not statuses:
        return NO_DATA_SOURCES_TEXT
    lines: list[str] = []
    for status in statuses:
        state = "" if status.available else f" (unavailable: {status.error})"
        lines.append(f"- {status.id}{state}: {status.description}")
    return "\n".join(lines)


def render_matches(keyword: str, matches: Sequence[SchemaMatch]) -> str:
    """Hasil `search_schema`: satu baris per tabel atau kolom.

    >>> print(render_matches("price", [SchemaMatch("public.items", "unit_price", "Per unit.")]))
    - public.items.unit_price: Per unit.
    """
    if not matches:
        return NO_MATCHES_TEMPLATE.format(keyword=keyword)
    lines: list[str] = []
    for match in matches:
        target = match.table if match.column is None else f"{match.table}.{match.column}"
        lines.append(f"- {target}" + (f": {match.comment}" if match.comment else ""))
    return "\n".join(lines)


def render_description(description: TableDescription) -> str:
    """Hasil `describe_table`: ringkasan tabel, kolom, relasi, lalu contoh baris."""
    table = description.table
    rows = "unknown" if table.estimated_rows is None else f"about {table.estimated_rows}"
    lines = [f"Table {table.ref.qualified} ({rows} rows)"]
    if table.comment:
        lines.append(table.comment)
    lines.append("\nColumns:")
    for column in description.columns:
        nullable = "" if column.nullable else ", not null"
        comment = f": {column.comment}" if column.comment else ""
        lines.append(f"- {column.name} ({column.type}{nullable}){comment}")
    if description.relations:
        lines.append("\nKeys and joins:")
        for relation in description.relations:
            lines.append(f"- {_render_relation(relation)}")
    lines.append("\nSample rows:")
    lines.append(render_rows(description.sample, PREVIEW_ROWS))
    return "\n".join(lines)


def render_profile(profile: TableProfile) -> str:
    """Hasil `profile_table`: satu blok per kolom."""
    lines = [f"Profile of {profile.table}: {profile.rows_profiled} rows"]
    if profile.sampled and profile.sample_percent is not None:
        lines.append(
            SAMPLED_NOTE_TEMPLATE.format(percent=profile.sample_percent, rows=profile.rows_profiled)
        )
    for column_profile in profile.columns:
        column = column_profile.column
        parts = [f"nulls {column_profile.null_fraction:.1%}"]
        if column_profile.distinct_count is not None:
            parts.append(f"distinct {column_profile.distinct_count}")
        if column_profile.minimum is not None or column_profile.maximum is not None:
            minimum = format_value(column_profile.minimum)
            parts.append(f"min {minimum}, max {format_value(column_profile.maximum)}")
        if column_profile.top_values:
            top = ", ".join(f"{format_value(v)} ({n})" for v, n in column_profile.top_values)
            parts.append(f"most common: {top}")
        lines.append(f"- {column.name} ({column.type}): " + "; ".join(parts))
    if profile.skipped_columns:
        lines.append(f"Not profiled (too many columns): {', '.join(profile.skipped_columns)}")
    return "\n".join(lines)


def render_query_result(result: QueryResult, path: str, truncated: bool, max_rows: int) -> str:
    """Hasil `run_sql`: path file, jumlah baris, tipe kolom, dan pratinjau.

    >>> print(render_query_result(QueryResult(["n"], ["int8"], [(3,)]), "data/q.parquet",
    ...                           False, 100))
    Saved 1 rows x 1 columns to data/q.parquet.
    Columns: n (int8)
    | n |
    | --- |
    | 3 |
    """
    lines = [f"Saved {len(result.rows)} rows x {len(result.columns)} columns to {path}."]
    if truncated:
        lines.append(
            f"The result was cut at {max_rows} rows. Aggregate or filter in SQL to see everything."
        )
    pairs = zip(result.columns, result.types, strict=True)
    typed = ", ".join(f"{name} ({kind})" for name, kind in pairs)
    lines.append(f"Columns: {typed}")
    lines.append(render_rows(result, PREVIEW_ROWS))
    return "\n".join(lines)


def render_rows(result: QueryResult, limit: int) -> str:
    """Tabel Markdown berisi `limit` baris pertama.

    >>> print(render_rows(QueryResult(["a", "b"], ["text", "int4"], [("x", None)]), 5))
    | a | b |
    | --- | --- |
    | x | NULL |
    """
    if not result.rows:
        return "(no rows)"
    lines = [
        "| " + " | ".join(result.columns) + " |",
        "| " + " | ".join("---" for _ in result.columns) + " |",
    ]
    for row in result.rows[:limit]:
        lines.append("| " + " | ".join(format_value(value) for value in row) + " |")
    hidden = len(result.rows) - limit
    if hidden > 0:
        lines.append(f"... {hidden} more rows")
    return "\n".join(lines)


def format_value(value: object) -> str:
    """Satu nilai untuk ditampilkan ke model, dipotong ke `CELL_MAX_CHARS`.

    >>> format_value(None), format_value(2/3), format_value("a|b")
    ('NULL', '0.666667', 'a/b')
    """
    if value is None:
        return NULL_TEXT
    if isinstance(value, float):
        text = format(value, FLOAT_FORMAT)
    elif isinstance(value, datetime | date):
        text = value.isoformat()
    else:
        text = str(value)
    text = text.replace("|", "/").replace("\n", " ")
    if len(text) > CELL_MAX_CHARS:
        return text[: CELL_MAX_CHARS - len(ELLIPSIS)] + ELLIPSIS
    return text


def _render_relation(relation: Relation) -> str:
    """Satu relasi: primary key atau foreign key dengan arah join."""
    columns = ", ".join(relation.columns)
    if relation.target is None:
        return f"{relation.kind} ({columns})"
    targets = ", ".join(relation.target_columns)
    return f"{relation.table}({columns}) -> {relation.target}({targets})"
