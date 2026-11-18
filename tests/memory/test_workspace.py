"""`PostgresWorkspace` di database asli (FR-47, NFR-9)."""

import pytest

from agent_service.files.workspace import WorkspaceFileNotFoundError, WorkspaceFileTooLargeError
from agent_service.memory.database import DatabaseEngineProvider
from agent_service.memory.workspace import PostgresWorkspace

MAX_BYTES = 64


async def test_files_are_written_overwritten_and_listed(database_url: str) -> None:
    async with DatabaseEngineProvider(database_url) as engine:
        workspace = PostgresWorkspace(engine, MAX_BYTES)
        await workspace.write("t1", "reports/q3.md", b"draft")
        await workspace.write("t1", "reports/q3.md", b"final!")
        await workspace.write("t1", "notes.txt", b"n")
        content = await workspace.read("t1", "reports/q3.md")
        listing = await workspace.list_files("t1")

    assert content == b"final!"
    assert [(file.path, file.size_bytes) for file in listing] == [
        ("notes.txt", 1),
        ("reports/q3.md", 6),
    ]


async def test_another_thread_cannot_read_the_files(database_url: str) -> None:
    async with DatabaseEngineProvider(database_url) as engine:
        workspace = PostgresWorkspace(engine, MAX_BYTES)
        await workspace.write("t1", "secret.txt", b"mine")

        with pytest.raises(WorkspaceFileNotFoundError):
            await workspace.read("t2", "secret.txt")
        assert await workspace.list_files("t2") == []


async def test_folder_prefix_is_matched_literally(database_url: str) -> None:
    async with DatabaseEngineProvider(database_url) as engine:
        workspace = PostgresWorkspace(engine, MAX_BYTES)
        await workspace.write("t1", "a_b/x.txt", b"1")
        await workspace.write("t1", "aXb/y.txt", b"2")
        listing = await workspace.list_files("t1", "a_b/")

    assert [file.path for file in listing] == ["a_b/x.txt"]


async def test_deleting_a_thread_removes_only_its_files(database_url: str) -> None:
    async with DatabaseEngineProvider(database_url) as engine:
        workspace = PostgresWorkspace(engine, MAX_BYTES)
        await workspace.write("t1", "a.txt", b"1")
        await workspace.write("t2", "b.txt", b"2")
        await workspace.delete_thread_data("t1")

        assert await workspace.list_files("t1") == []
        assert [file.path for file in await workspace.list_files("t2")] == ["b.txt"]


async def test_files_over_the_limit_are_rejected(database_url: str) -> None:
    async with DatabaseEngineProvider(database_url) as engine:
        workspace = PostgresWorkspace(engine, MAX_BYTES)

        with pytest.raises(WorkspaceFileTooLargeError):
            await workspace.write("t1", "big.bin", b"x" * (MAX_BYTES + 1))


async def test_listing_uses_byte_order(database_url: str) -> None:
    async with DatabaseEngineProvider(database_url) as engine:
        workspace = PostgresWorkspace(engine, MAX_BYTES)
        for path in ("uploads/sales.csv", "uploads/sales-zz.csv", "uploads/sales-aa.csv"):
            await workspace.write("t1", path, b"1")
        listing = await workspace.list_files("t1")

    assert [file.path for file in listing] == [
        "uploads/sales-aa.csv",
        "uploads/sales-zz.csv",
        "uploads/sales.csv",
    ]
