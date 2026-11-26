"""Tool `run_python` dan `run_shell` (FR-49, NFR-10, F37): kode model dijalankan di sandbox.

Kode tidak pernah dijalankan di proses service. Tool menyalin seluruh workspace thread ke
`/workspace` sandbox, menjalankan kode lewat `Sandbox` dari runtime context, lalu menyimpan file
yang baru atau berubah kembali ke workspace. Jika project mewajibkan persetujuan
(`ProjectSettings.tool_approval = "always"`), user ditanya lewat `interrupt()` sebelum eksekusi.

Exit code bukan nol dan timeout dikembalikan sebagai `ToolMessage` berstatus `"error"` (FR-59),
supaya `ToolFailureGuard` menghitungnya tanpa mencocokkan teks. Isinya tetap observasi lengkap.
"""

from collections.abc import Mapping
from typing import Any, Final

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, ToolException, tool
from langgraph.prebuilt import ToolRuntime
from langgraph.types import interrupt

from agent_service.core.constants import PROJECT_TOOL_APPROVAL_CONFIG_KEY
from agent_service.files.workspace import (
    WorkspaceFileTooLargeError,
    WorkspacePathError,
    normalize_workspace_path,
)
from agent_service.harness.runtime import HarnessContext
from agent_service.harness.tools.files import CONFIGURABLE_KEY, WorkspaceScope, workspace_scope
from agent_service.harness.tools.memory import APPROVAL_LEAD_WORDS, is_approval
from agent_service.sandbox.model import (
    TRANSFER_MAX_BYTES,
    ExecutionRequest,
    ExecutionResult,
    Language,
    SandboxError,
)

RUN_PYTHON_TOOL_NAME: Final = "run_python"
RUN_SHELL_TOOL_NAME: Final = "run_shell"
APPROVAL_REQUIRED: Final = "always"
SUCCESS_EXIT_CODE: Final = 0
ERROR_STATUS: Final = "error"
EXECUTION_LEAD_WORDS: Final = APPROVAL_LEAD_WORDS | {"run", "execute", "jalankan"}
CODE_FENCES: Final[Mapping[Language, str]] = {"python": "python", "shell": "sh"}
SANDBOX_UNAVAILABLE_TEXT: Final = "Code execution is not available in this conversation."
# Teks yang dilihat user (pertanyaan interrupt) berbahasa Inggris, sama seperti teks UI lain.
APPROVAL_QUESTION: Final = (
    "Run this {language} code in the sandbox?\n\n```{fence}\n{code}\n```\n\n"
    'Reply "yes" to run it, or anything else to cancel.'
)
DECLINED_TEXT: Final = (
    'The user did not approve running this code, so it did not run. Their reply: "{reply}". '
    "Respond to their reply."
)


def approval_required(config: Mapping[str, Any] | None) -> bool:  # Any: RunnableConfig
    """Cek apakah project run ini mewajibkan persetujuan sebelum eksekusi.

    >>> approval_required({"configurable": {"project_tool_approval": "always"}})
    True
    >>> approval_required({"configurable": {}}), approval_required(None)
    (False, False)
    """
    configurable = (config or {}).get(CONFIGURABLE_KEY) or {}
    return configurable.get(PROJECT_TOOL_APPROVAL_CONFIG_KEY) == APPROVAL_REQUIRED


def render_result(result: ExecutionResult, saved: list[str], skipped: list[str]) -> str:
    """Hasil eksekusi untuk model: status, stdout, stderr, dan file yang disimpan.

    >>> print(render_result(ExecutionResult(exit_code=0, stdout="4\\n"), ["chart.png"], []))
    Exit code: 0
    stdout:
    4
    <BLANKLINE>
    Files saved to the workspace: chart.png
    """
    lines = [_status_line(result)]
    if result.stdout:
        lines.append(f"stdout:\n{result.stdout}")
    if result.stderr:
        lines.append(f"stderr:\n{result.stderr}")
    if saved:
        lines.append(f"Files saved to the workspace: {', '.join(saved)}")
    if skipped:
        lines.append(f"Files not saved (invalid path or too large): {', '.join(skipped)}")
    if result.output_truncated:
        lines.append("[Output or files were truncated because they were too large.]")
    return "\n".join(lines)


def create_execution_tools(timeout_seconds: int) -> list[BaseTool]:
    """Buat tool `run_python` dan `run_shell`.

    Function, bukan class: factory `@tool` (AGENTS.md § Class vs Function). Sandbox dibaca dari
    runtime context di setiap pemanggilan.

    Args:
        timeout_seconds: Batas waktu satu eksekusi (`SANDBOX_TIMEOUT_SECONDS`).
    """

    @tool(RUN_PYTHON_TOOL_NAME)
    async def run_python(code: str, runtime: ToolRuntime[HarnessContext]) -> str | ToolMessage:
        """Run Python code in an isolated sandbox without internet access.

        The working directory contains every file in the conversation workspace, and files you
        write there are saved back to the workspace. pandas, numpy, and matplotlib are installed;
        save charts with matplotlib to a file such as "chart.png", then share it with share_file.

        Args:
            code: Complete Python script to run. Print the results you need.
        """
        return await _run(RUN_PYTHON_TOOL_NAME, "python", code, runtime, timeout_seconds)

    @tool(RUN_SHELL_TOOL_NAME)
    async def run_shell(command: str, runtime: ToolRuntime[HarnessContext]) -> str | ToolMessage:
        """Run a shell command in an isolated sandbox without internet access.

        The working directory contains every file in the conversation workspace, and files
        written there are saved back to the workspace.

        Args:
            command: Shell command or short script, run with sh.
        """
        return await _run(RUN_SHELL_TOOL_NAME, "shell", command, runtime, timeout_seconds)

    return [run_python, run_shell]


async def _run(
    tool_name: str,
    language: Language,
    code: str,
    runtime: ToolRuntime[HarnessContext],
    timeout_seconds: int,
) -> str | ToolMessage:
    """Minta persetujuan jika perlu, jalankan kode di sandbox, lalu simpan file hasilnya.

    Returns:
        Teks hasil, atau `ToolMessage` berstatus error jika kode gagal (exit code, timeout).
    """
    scope = workspace_scope(runtime)
    sandbox = scope.context.sandbox
    if sandbox is None:
        raise ToolException(SANDBOX_UNAVAILABLE_TEXT)
    if approval_required(runtime.config):
        question = APPROVAL_QUESTION.format(
            language=language, fence=CODE_FENCES[language], code=code
        )
        reply = interrupt(question)
        if not is_approval(reply, EXECUTION_LEAD_WORDS):
            return DECLINED_TEXT.format(reply=reply)
    request = ExecutionRequest(
        language=language,
        code=code,
        files=await _workspace_files(scope),
        timeout_seconds=timeout_seconds,
    )
    try:
        result = await sandbox.execute(request)
    except SandboxError as error:
        raise ToolException(str(error)) from error
    saved, skipped = await _save_outputs(scope, result.files)
    content = render_result(result, saved, skipped)
    if not execution_failed(result) or runtime.tool_call_id is None:
        return content
    return ToolMessage(
        content=content, tool_call_id=runtime.tool_call_id, name=tool_name, status=ERROR_STATUS
    )


def execution_failed(result: ExecutionResult) -> bool:
    """Cek apakah eksekusi gagal: timeout atau exit code bukan nol.

    >>> [execution_failed(ExecutionResult(exit_code=code)) for code in (0, 1)]
    [False, True]
    >>> execution_failed(ExecutionResult(exit_code=None, timed_out=True))
    True
    """
    return result.timed_out or result.exit_code != SUCCESS_EXIT_CODE


async def _workspace_files(scope: WorkspaceScope) -> dict[str, bytes]:
    """Isi workspace thread untuk disalin ke sandbox, dibatasi total `TRANSFER_MAX_BYTES`."""
    workspace = scope.context.workspace
    files: dict[str, bytes] = {}
    total = 0
    for file in await workspace.list_files(scope.thread_id):
        total += file.size_bytes
        if total > TRANSFER_MAX_BYTES:
            break
        files[file.path] = await workspace.read(scope.thread_id, file.path)
    return files


async def _save_outputs(
    scope: WorkspaceScope, outputs: Mapping[str, bytes]
) -> tuple[list[str], list[str]]:
    """Simpan file baru atau berubah dari sandbox ke workspace.

    Returns:
        Path yang disimpan, dan path yang dilewati (tidak valid atau terlalu besar).
    """
    saved: list[str] = []
    skipped: list[str] = []
    for raw_path, content in outputs.items():
        try:
            path = normalize_workspace_path(raw_path)
            await scope.context.workspace.write(scope.thread_id, path, content)
        except (WorkspacePathError, WorkspaceFileTooLargeError):
            skipped.append(raw_path)
            continue
        saved.append(path)
    return saved, skipped


def _status_line(result: ExecutionResult) -> str:
    """Baris status: kode keluar, atau pemberitahuan timeout."""
    if result.timed_out:
        return "Timed out: the process was stopped before it finished."
    return f"Exit code: {result.exit_code}"
