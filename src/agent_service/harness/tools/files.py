"""Tool file workspace (FR-47, F36): `read_file`, `write_file`, `edit_file`, `list_files`, `grep`,
dan `share_file`.

Semua tool bekerja di workspace thread run yang sedang berjalan. `thread_id` dan `user_id` dibaca
dari config yang ditetapkan service, dan workspace dari `HarnessContext` (runtime context), jadi
model tidak bisa memilih thread lain. Kesalahan input model menjadi `ToolException`, yang
dikembalikan ke model sebagai pesan error.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Final

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, ToolException, tool
from langgraph.prebuilt import ToolRuntime

from agent_service.core.constants import ARTIFACTS_KWARG, USER_ID_CONFIG_KEY
from agent_service.files.artifacts import ArtifactTooLargeError
from agent_service.files.workspace import (
    WorkspaceFileNotFoundError,
    WorkspaceFileTooLargeError,
    WorkspacePathError,
    normalize_workspace_folder,
    normalize_workspace_path,
)
from agent_service.harness.runtime import HarnessContext
from agent_service.memory.artifacts import ArtifactRecord

READ_FILE_TOOL_NAME: Final = "read_file"
WRITE_FILE_TOOL_NAME: Final = "write_file"
EDIT_FILE_TOOL_NAME: Final = "edit_file"
LIST_FILES_TOOL_NAME: Final = "list_files"
GREP_TOOL_NAME: Final = "grep"
SHARE_FILE_TOOL_NAME: Final = "share_file"
# Tool yang membatasi outputnya sendiri, jadi tidak dipindah ke workspace oleh offloader.
SELF_LIMITING_TOOL_NAMES: Final = frozenset(
    {READ_FILE_TOOL_NAME, LIST_FILES_TOOL_NAME, GREP_TOOL_NAME}
)

DEFAULT_READ_LIMIT_LINES: Final = 200
LINE_NUMBER_WIDTH: Final = 6
LIST_MAX_ENTRIES: Final = 200
GREP_MAX_MATCHES: Final = 100
GREP_LINE_MAX_CHARS: Final = 200
TEXT_ENCODING: Final = "utf-8"
CONFIGURABLE_KEY: Final = "configurable"
THREAD_ID_KEY: Final = "thread_id"
WORKSPACE_UNAVAILABLE_TEXT: Final = "The workspace is not available in this conversation."


@dataclass(frozen=True)
class WorkspaceScope:
    """Workspace, thread, dan pemilik untuk satu pemanggilan tool."""

    context: HarnessContext
    thread_id: str
    user_id: str


def workspace_scope(runtime: ToolRuntime[HarnessContext]) -> WorkspaceScope:
    """Ambil workspace dan identitas run dari runtime tool.

    Raises:
        ToolException: Jika run tidak membawa `HarnessContext` atau thread.
    """
    context = runtime.context
    configurable: Mapping[str, Any] = (runtime.config or {}).get(CONFIGURABLE_KEY) or {}
    thread_id = configurable.get(THREAD_ID_KEY)
    if not isinstance(context, HarnessContext) or not isinstance(thread_id, str):
        raise ToolException(WORKSPACE_UNAVAILABLE_TEXT)
    user_id = configurable.get(USER_ID_CONFIG_KEY)
    return WorkspaceScope(context, thread_id, user_id if isinstance(user_id, str) else "")


def checked_path(path: str) -> str:
    """Path workspace yang sudah dinormalisasi.

    Raises:
        ToolException: Jika path keluar dari workspace atau tidak valid.
    """
    try:
        return normalize_workspace_path(path)
    except WorkspacePathError as error:
        raise ToolException(str(error)) from error


def decode_text(path: str, content: bytes) -> str:
    """Isi file sebagai teks UTF-8.

    Raises:
        ToolException: Jika file biner (bukan UTF-8), dengan saran membagikannya.
    """
    try:
        return content.decode(TEXT_ENCODING)
    except UnicodeDecodeError as error:
        raise ToolException(
            f"{path} is a binary file ({len(content)} bytes) and cannot be read as text. "
            f"Use {SHARE_FILE_TOOL_NAME} to give it to the user."
        ) from error


def number_lines(text: str, offset: int, limit: int, max_chars: int) -> str:
    """Potongan baris bernomor, dengan catatan jika masih ada baris berikutnya.

    >>> number_lines("a\\nb\\nc", offset=2, limit=1, max_chars=1000).splitlines()
    ['     2\\tb', '[Lines 2-2 of 3. Continue with offset=3.]']
    """
    lines = text.splitlines()
    start = max(offset, 1)
    selected: list[str] = []
    used_chars = 0
    last = start - 1
    for number in range(start, min(start + limit, len(lines) + 1)):
        rendered = f"{number:>{LINE_NUMBER_WIDTH}}\t{lines[number - 1]}"
        if selected and used_chars + len(rendered) > max_chars:
            break
        selected.append(rendered)
        used_chars += len(rendered) + 1
        last = number
    if not selected:
        return f"[No lines at offset {start}; the file has {len(lines)} lines.]"
    body = "\n".join(selected)
    if last < len(lines):
        body += f"\n[Lines {start}-{last} of {len(lines)}. Continue with offset={last + 1}.]"
    return body


def replace_once(text: str, old_text: str, new_text: str) -> str:
    """Ganti tepat satu kemunculan `old_text`.

    >>> replace_once("a b a", "b", "c")
    'a c a'

    Raises:
        ToolException: Jika `old_text` kosong, tidak ditemukan, atau muncul lebih dari sekali.
    """
    if not old_text:
        raise ToolException("old_text must not be empty")
    count = text.count(old_text)
    if count == 0:
        raise ToolException(
            "old_text was not found in the file. Read the file and copy it exactly."
        )
    if count > 1:
        raise ToolException(
            f"old_text appears {count} times. Include more surrounding text so it is unique."
        )
    return text.replace(old_text, new_text, 1)


def artifact_reference(record: ArtifactRecord) -> dict[str, str | int]:
    """Referensi artifact berbentuk `ArtifactRef` untuk `additional_kwargs` message."""
    return {
        "id": record.artifact_id,
        "name": record.name,
        "mime_type": record.mime_type,
        "size": record.size_bytes,
    }


def create_workspace_tools(max_output_chars: int) -> list[BaseTool]:
    """Buat tool file workspace.

    Function, bukan class: factory `@tool` (AGENTS.md § Class vs Function). Workspace dibaca dari
    runtime context di setiap pemanggilan, jadi tool yang sama dipakai semua run.

    Args:
        max_output_chars: Batas output `read_file`, `list_files`, dan `grep`.
    """
    return [
        _read_file_tool(max_output_chars),
        _write_file_tool(),
        _edit_file_tool(),
        _list_files_tool(max_output_chars),
        _grep_tool(max_output_chars),
        _share_file_tool(),
    ]


def _read_file_tool(max_output_chars: int) -> BaseTool:
    @tool(READ_FILE_TOOL_NAME)
    async def read_file(
        path: str,
        runtime: ToolRuntime[HarnessContext],
        offset: int = 1,
        limit: int = DEFAULT_READ_LIMIT_LINES,
    ) -> str:
        """Read a text file from the conversation workspace, with line numbers.

        Large files are returned in parts; continue with the offset given at the end.

        Args:
            path: File path relative to the workspace, for example "uploads/sales.csv".
            offset: First line to read, starting at 1.
            limit: Maximum number of lines to return.
        """
        scope = workspace_scope(runtime)
        file_path = checked_path(path)
        content = await _read(scope, file_path)
        return number_lines(decode_text(file_path, content), offset, limit, max_output_chars)

    return read_file


def _write_file_tool() -> BaseTool:
    @tool(WRITE_FILE_TOOL_NAME)
    async def write_file(path: str, content: str, runtime: ToolRuntime[HarnessContext]) -> str:
        """Create or overwrite a text file in the conversation workspace.

        Args:
            path: File path relative to the workspace, for example "reports/summary.md".
            content: Full text content of the file.
        """
        scope = workspace_scope(runtime)
        file_path = checked_path(path)
        data = content.encode(TEXT_ENCODING)
        await _write(scope, file_path, data)
        return f"Wrote {len(data)} bytes to {file_path}."

    return write_file


def _edit_file_tool() -> BaseTool:
    @tool(EDIT_FILE_TOOL_NAME)
    async def edit_file(
        path: str, old_text: str, new_text: str, runtime: ToolRuntime[HarnessContext]
    ) -> str:
        """Replace one exact piece of text in a workspace file.

        old_text must appear exactly once; include surrounding lines to make it unique.

        Args:
            path: File path relative to the workspace.
            old_text: Exact text to replace, copied from the file.
            new_text: Replacement text.
        """
        scope = workspace_scope(runtime)
        file_path = checked_path(path)
        text = decode_text(file_path, await _read(scope, file_path))
        await _write(scope, file_path, replace_once(text, old_text, new_text).encode(TEXT_ENCODING))
        return f"Edited {file_path}."

    return edit_file


def _list_files_tool(max_output_chars: int) -> BaseTool:
    @tool(LIST_FILES_TOOL_NAME)
    async def list_files(runtime: ToolRuntime[HarnessContext], folder: str = "") -> str:
        """List files in the conversation workspace, with their sizes.

        Args:
            folder: Optional folder to list, for example "uploads". Empty lists every file.
        """
        scope = workspace_scope(runtime)
        prefix = _checked_folder(folder)
        files = await scope.context.workspace.list_files(scope.thread_id, prefix)
        if not files:
            return "No files in the workspace." if not prefix else f"No files in {prefix}."
        lines = [f"{file.path} ({file.size_bytes} bytes)" for file in files[:LIST_MAX_ENTRIES]]
        if len(files) > LIST_MAX_ENTRIES:
            lines.append(f"[{len(files) - LIST_MAX_ENTRIES} more files not shown.]")
        return _limit("\n".join(lines), max_output_chars)

    return list_files


def _grep_tool(max_output_chars: int) -> BaseTool:
    @tool(GREP_TOOL_NAME)
    async def grep(
        text: str,
        runtime: ToolRuntime[HarnessContext],
        folder: str = "",
        ignore_case: bool = False,
    ) -> str:
        """Find lines containing exact text in workspace files (not a regular expression).

        Args:
            text: Text to search for, matched literally.
            folder: Optional folder to search in. Empty searches every file.
            ignore_case: Match regardless of upper or lower case.
        """
        if not text:
            raise ToolException("text must not be empty")
        scope = workspace_scope(runtime)
        prefix = _checked_folder(folder)
        matcher = _literal_matcher(text, ignore_case)
        matches: list[str] = []
        for file in await scope.context.workspace.list_files(scope.thread_id, prefix):
            content = await _read(scope, file.path)
            matches.extend(_matching_lines(file.path, content, matcher))
            if len(matches) >= GREP_MAX_MATCHES:
                break
        if not matches:
            return f"No lines contain {text!r}."
        shown = matches[:GREP_MAX_MATCHES]
        if len(matches) > GREP_MAX_MATCHES:
            shown.append(f"[Stopped after {GREP_MAX_MATCHES} matches.]")
        return _limit("\n".join(shown), max_output_chars)

    return grep


def _share_file_tool() -> BaseTool:
    @tool(SHARE_FILE_TOOL_NAME)
    async def share_file(path: str, runtime: ToolRuntime[HarnessContext]) -> ToolMessage:
        """Give a workspace file to the user as a downloadable attachment.

        Use this for files the user asked for, such as reports, data exports, or charts.

        Args:
            path: File path relative to the workspace.
        """
        scope = workspace_scope(runtime)
        file_path = checked_path(path)
        content = await _read(scope, file_path)
        name = PurePosixPath(file_path).name
        try:
            record = await scope.context.artifacts.publish(
                scope.user_id, scope.thread_id, name, content
            )
        except ArtifactTooLargeError as error:
            raise ToolException(str(error)) from error
        return ToolMessage(
            content=f"Shared {file_path} with the user as {record.name}.",
            tool_call_id=runtime.tool_call_id or "",
            additional_kwargs={ARTIFACTS_KWARG: [artifact_reference(record)]},
        )

    return share_file


async def _read(scope: WorkspaceScope, path: str) -> bytes:
    """Isi file workspace, dengan error yang bisa dibaca model."""
    try:
        return await scope.context.workspace.read(scope.thread_id, path)
    except WorkspaceFileNotFoundError as error:
        raise ToolException(f"{error}. Use {LIST_FILES_TOOL_NAME} to see the files.") from error


async def _write(scope: WorkspaceScope, path: str, content: bytes) -> None:
    """Tulis file workspace, dengan error ukuran yang bisa dibaca model."""
    try:
        await scope.context.workspace.write(scope.thread_id, path, content)
    except WorkspaceFileTooLargeError as error:
        raise ToolException(str(error)) from error


def _checked_folder(folder: str) -> str:
    """Prefix folder yang sudah dinormalisasi, dengan error yang bisa dibaca model."""
    try:
        return normalize_workspace_folder(folder)
    except WorkspacePathError as error:
        raise ToolException(str(error)) from error


def _literal_matcher(text: str, ignore_case: bool) -> Callable[[str], bool]:
    """Pencocok substring persis. Tanpa regex, pola dari model tidak bisa membuat CPU macet."""
    if not ignore_case:
        return lambda line: text in line
    needle = text.casefold()
    return lambda line: needle in line.casefold()


def _matching_lines(path: str, content: bytes, matcher: Callable[[str], bool]) -> list[str]:
    """Baris yang cocok dalam satu file, berformat `path:nomor: isi`. File biner dilewati."""
    try:
        text = content.decode(TEXT_ENCODING)
    except UnicodeDecodeError:
        return []
    matches: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if matcher(line):
            matches.append(f"{path}:{number}: {line.strip()[:GREP_LINE_MAX_CHARS]}")
            if len(matches) >= GREP_MAX_MATCHES:
                break
    return matches


def _limit(text: str, max_chars: int) -> str:
    """Potong output ke `max_chars` dengan catatan."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[Output truncated.]"
