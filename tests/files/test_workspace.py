"""Workspace in-memory dan validasi path (FR-47). Acceptance F36: path traversal ditolak."""

import ast
from pathlib import Path

import pytest

import agent_service.files
from agent_service.files.workspace import (
    InMemoryWorkspace,
    WorkspaceFileNotFoundError,
    WorkspaceFileTooLargeError,
    WorkspacePathError,
    normalize_workspace_folder,
    normalize_workspace_path,
)

FILES_DIR = Path(agent_service.files.__file__).parent
FORBIDDEN_PREFIXES = (
    "agent_service.memory",
    "agent_service.harness",
    "agent_service.agents",
    "agent_service.service",
    "agent_service.schema",
    "langchain",
    "langgraph",
    "fastapi",
)


@pytest.mark.parametrize(
    "path",
    [
        "../secret.txt",
        "notes/../../secret.txt",
        "/etc/passwd",
        "\\\\server\\share\\x",
        "C:/Windows/win.ini",
        "c:relative.txt",
        "",
        "   ",
        "./",
        "bad\x00name",
        "line\nbreak.txt",
    ],
)
def test_paths_that_could_leave_the_workspace_are_rejected(path: str) -> None:
    with pytest.raises(WorkspacePathError):
        normalize_workspace_path(path)


def test_long_paths_are_rejected() -> None:
    with pytest.raises(WorkspacePathError):
        normalize_workspace_path("a/" * 300 + "b.txt")


def test_folders_are_normalized_with_a_trailing_slash() -> None:
    assert normalize_workspace_folder("uploads") == "uploads/"
    assert normalize_workspace_folder("/") == ""
    with pytest.raises(WorkspacePathError):
        normalize_workspace_folder("../uploads")


async def test_threads_have_separate_workspaces() -> None:
    workspace = InMemoryWorkspace(max_file_bytes=100)
    await workspace.write("t1", "notes.md", b"mine")

    with pytest.raises(WorkspaceFileNotFoundError):
        await workspace.read("t2", "notes.md")
    assert await workspace.list_files("t2") == []
    assert await workspace.read("t1", "notes.md") == b"mine"


async def test_listing_filters_by_folder_and_deleting_clears_the_thread() -> None:
    workspace = InMemoryWorkspace(max_file_bytes=100)
    await workspace.write("t1", "uploads/a.csv", b"1")
    await workspace.write("t1", "uploads-old/b.csv", b"22")
    await workspace.write("t1", "report.md", b"333")

    uploads = await workspace.list_files("t1", "uploads/")
    await workspace.delete_thread_data("t1")

    assert [(file.path, file.size_bytes) for file in uploads] == [("uploads/a.csv", 1)]
    assert await workspace.list_files("t1") == []


async def test_files_over_the_limit_are_rejected() -> None:
    workspace = InMemoryWorkspace(max_file_bytes=3)

    with pytest.raises(WorkspaceFileTooLargeError):
        await workspace.write("t1", "big.bin", b"1234")


def absolute_imports(source_file: Path) -> list[str]:
    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.append(node.module)
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
    return modules


def test_files_layer_imports_only_core_and_io_libraries() -> None:
    violations: list[str] = []
    for source_file in sorted(FILES_DIR.rglob("*.py")):
        for module in absolute_imports(source_file):
            if module.startswith(FORBIDDEN_PREFIXES):
                violations.append(f"{source_file.name}: {module}")

    assert violations == []
