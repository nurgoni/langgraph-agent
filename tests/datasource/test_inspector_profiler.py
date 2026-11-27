"""`SchemaInspector` dan `TableProfiler` di kedua dataset demo, dengan kode yang sama (FR-51)."""

from collections.abc import AsyncIterator

import pytest

from agent_service.datasource.inspector import SchemaInspector
from agent_service.datasource.model import TableNotFoundError
from agent_service.datasource.profiler import TableProfiler
from agent_service.datasource.source import SqlDataSource

TIMEOUT_SECONDS = 10
EXACT_MAX_ROWS = 1_000_000


@pytest.fixture
async def sources(demo_database_urls: dict[str, str]) -> AsyncIterator[dict[str, SqlDataSource]]:
    opened = {
        name: SqlDataSource(name, url, TIMEOUT_SECONDS) for name, url in demo_database_urls.items()
    }
    for source in opened.values():
        await source.open()
    yield opened
    for source in opened.values():
        await source.close()


@pytest.mark.parametrize(
    ("dataset", "tables"),
    [
        ("shop", ["customers", "order_items", "orders", "products", "refunds"]),
        ("sensors", ["devices", "readings", "sites"]),
    ],
)
async def test_tables_lists_readable_tables_with_estimates(
    sources: dict[str, SqlDataSource], dataset: str, tables: list[str]
) -> None:
    listed = await SchemaInspector(sources[dataset]).tables()

    assert [info.ref.name for info in listed] == tables
    assert all(info.estimated_rows is not None and info.comment for info in listed)


@pytest.mark.parametrize(
    ("dataset", "table", "join"),
    [
        ("shop", "orders", ("public.orders", ("customer_id",), "public.customers")),
        ("sensors", "readings", ("public.readings", ("device_id",), "public.devices")),
    ],
)
async def test_describe_shows_columns_join_paths_and_sample_rows(
    sources: dict[str, SqlDataSource],
    dataset: str,
    table: str,
    join: tuple[str, tuple[str, ...], str],
) -> None:
    description = await SchemaInspector(sources[dataset]).describe(table)

    foreign_keys = [
        (r.table, r.columns, r.target) for r in description.relations if r.kind == "foreign key"
    ]
    assert join in foreign_keys
    assert description.columns[0].name.endswith("_id")
    assert any(column.comment for column in description.columns)
    assert len(description.sample.rows) == 5


async def test_describe_lists_incoming_foreign_keys_and_primary_key(
    sources: dict[str, SqlDataSource],
) -> None:
    description = await SchemaInspector(sources["shop"]).describe("public.customers")

    kinds = {(r.kind, r.table, r.columns) for r in description.relations}
    assert ("primary key", "public.customers", ("customer_id",)) in kinds
    assert ("foreign key", "public.orders", ("customer_id",)) in kinds


async def test_unknown_table_suggests_similar_names(sources: dict[str, SqlDataSource]) -> None:
    with pytest.raises(TableNotFoundError, match="public.orders"):
        await SchemaInspector(sources["shop"]).describe("order")


async def test_table_names_are_matched_to_the_catalog_not_injected(
    sources: dict[str, SqlDataSource],
) -> None:
    with pytest.raises(TableNotFoundError):
        await SchemaInspector(sources["shop"]).describe("orders; DROP TABLE orders")


@pytest.mark.parametrize(
    ("dataset", "keyword", "expected"),
    [
        ("shop", "refund", ("public.refunds", None)),
        ("shop", "contact email", ("public.customers", "email")),
        ("sensors", "unit of the device", ("public.readings", "value")),
        ("sensors", "50%_", None),
    ],
)
async def test_search_matches_names_and_comments(
    sources: dict[str, SqlDataSource],
    dataset: str,
    keyword: str,
    expected: tuple[str, str | None] | None,
) -> None:
    matches = await SchemaInspector(sources[dataset]).search(keyword)

    found = [(match.table, match.column) for match in matches]
    assert (expected in found) if expected else found == []


async def test_profile_reports_nulls_distinct_ranges_and_top_values(
    sources: dict[str, SqlDataSource],
) -> None:
    inspector = SchemaInspector(sources["shop"])
    profiler = TableProfiler(sources["shop"], inspector, EXACT_MAX_ROWS)

    profile = await profiler.profile("customers", ["email", "region", "signup_date"])

    email, region, signup = profile.columns
    assert (profile.rows_profiled, profile.sampled) == (2000, False)
    assert 0.05 < email.null_fraction < 0.11
    assert region.distinct_count == 4
    assert {value for value, _ in region.top_values} == {"north", "south", "east", "west"}
    assert str(signup.minimum) >= "2024-01-01"
    assert signup.top_values == []


async def test_large_tables_are_profiled_from_a_sample(sources: dict[str, SqlDataSource]) -> None:
    inspector = SchemaInspector(sources["sensors"])
    profiler = TableProfiler(sources["sensors"], inspector, exact_max_rows=20_000)

    profile = await profiler.profile("readings", ["value"])

    assert profile.sampled
    assert profile.sample_percent is not None and profile.sample_percent < 15
    assert 0 < profile.rows_profiled < 100_000
    assert profile.columns[0].null_fraction < 0.01


async def test_unknown_columns_are_reported_with_the_table_columns(
    sources: dict[str, SqlDataSource],
) -> None:
    profiler = TableProfiler(sources["sensors"], SchemaInspector(sources["sensors"]), 1000)

    with pytest.raises(TableNotFoundError, match="recorded_at"):
        await profiler.profile("readings", ["reading_time"])
