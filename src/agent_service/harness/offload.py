"""Pemindahan output tool yang terlalu besar ke workspace (FR-48, F36).

`ToolOutputOffloader` dipasang di `ToolNode(awrap_tool_call=...)`. Output tool yang melebihi
`TOOL_OUTPUT_MAX_TOKENS` ditulis ke `tool-outputs/<tool_call_id>.txt` di workspace thread, lalu
model menerima cuplikan awal dan path file itu, sehingga bisa membaca sisanya dengan `read_file`
atau `grep` tanpa menghabiskan anggaran konteks.
"""

import logging
import re
from collections.abc import Awaitable, Callable
from typing import Final

from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from agent_service.harness.context_policy import CHARS_PER_TOKEN
from agent_service.harness.runtime import HarnessContext
from agent_service.harness.tools.files import (
    CONFIGURABLE_KEY,
    GREP_TOOL_NAME,
    READ_FILE_TOOL_NAME,
    SELF_LIMITING_TOOL_NAMES,
    THREAD_ID_KEY,
)

logger = logging.getLogger(__name__)

TOOL_OUTPUTS_FOLDER: Final = "tool-outputs"
# Cuplikan yang tetap dikirim ke model: seperempat batas, supaya sisa anggaran untuk jawaban.
PREVIEW_DIVISOR: Final = 4
TEXT_ENCODING: Final = "utf-8"
# ID tool call dari provider bisa berisi karakter apa pun; nama file hanya memakai karakter aman.
UNSAFE_FILENAME_CHARS: Final = re.compile(r"[^A-Za-z0-9_-]")

type ToolResult = ToolMessage | Command
type ToolExecutor = Callable[[ToolCallRequest], Awaitable[ToolResult]]


class ToolOutputOffloader:
    """Membatasi ukuran output tool yang masuk riwayat percakapan.

    Class karena menyimpan batas dari `Settings` dan dipakai sebagai callable `awrap_tool_call`.
    Tanpa workspace di runtime context, output besar dipotong saja, tanpa disimpan.
    """

    def __init__(self, max_tokens: int) -> None:
        """Inisialisasi offloader.

        Args:
            max_tokens: Batas output satu tool call (`TOOL_OUTPUT_MAX_TOKENS`).
        """
        self._max_chars = max_tokens * CHARS_PER_TOKEN
        self._preview_chars = self._max_chars // PREVIEW_DIVISOR

    async def __call__(self, request: ToolCallRequest, execute: ToolExecutor) -> ToolResult:
        """Jalankan tool, lalu pindahkan outputnya ke workspace jika terlalu besar."""
        result = await execute(request)
        if not isinstance(result, ToolMessage) or not isinstance(result.content, str):
            return result
        if result.name in SELF_LIMITING_TOOL_NAMES or len(result.content) <= self._max_chars:
            return result
        path = await self._save(request, result)
        return result.model_copy(update={"content": self._preview(result.content, path)})

    async def _save(self, request: ToolCallRequest, result: ToolMessage) -> str | None:
        """Tulis output utuh ke workspace thread. `None` jika run tidak punya workspace."""
        context = request.runtime.context
        configurable = (request.runtime.config or {}).get(CONFIGURABLE_KEY) or {}
        thread_id = configurable.get(THREAD_ID_KEY)
        if not isinstance(context, HarnessContext) or not isinstance(thread_id, str):
            return None
        path = output_path(result.tool_call_id)
        await context.workspace.write(thread_id, path, str(result.content).encode(TEXT_ENCODING))
        logger.info("Offloaded %d chars of %s output to %s", len(result.content), result.name, path)
        return path

    def _preview(self, content: str, path: str | None) -> str:
        """Cuplikan awal output, beserta petunjuk untuk membaca sisanya."""
        preview = content[: self._preview_chars]
        total_tokens = len(content) // CHARS_PER_TOKEN
        if path is None:
            return f"{preview}\n\n[Output truncated: about {total_tokens} tokens in total.]"
        return (
            f"{preview}\n\n[Output too large (about {total_tokens} tokens). The full output is "
            f"saved in the workspace at {path}. Use {READ_FILE_TOOL_NAME} with an offset or "
            f"{GREP_TOOL_NAME} to read the rest.]"
        )


def output_path(tool_call_id: str) -> str:
    """Path file output satu tool call, dengan ID yang disanitasi.

    >>> output_path("call_9f/../x")
    'tool-outputs/call_9f____x.txt'
    """
    safe_id = UNSAFE_FILENAME_CHARS.sub("_", tool_call_id) or "output"
    return f"{TOOL_OUTPUTS_FOLDER}/{safe_id}.txt"
