"""Batas kegagalan beruntun per tool (FR-59, ADR 0007, F47).

`ToolFailureGuard` dipasang di `ToolNode(awrap_tool_call=...)`. Sebelum tool dijalankan, guard
menghitung kegagalan beruntun tool itu dari message giliran yang sedang berjalan (sejak pesan
human terakhir). Jika sudah mencapai batas, tool tidak dijalankan dan model menerima
`ToolMessage` error yang memintanya berhenti mencoba dan menjelaskan error ke user.

Hitungan dibaca dari state, bukan counter di memori, jadi tetap benar saat run dilanjutkan dari
interrupt atau dijalankan ulang dari checkpoint. Kegagalan adalah `ToolMessage` berstatus
`"error"`: `ToolException` yang ditangkap `ToolNode`, atau penanda eksplisit dari tool eksekusi
(exit code bukan nol, timeout). Tool call paralel dalam satu jawaban model membaca state yang
sama, jadi satu batch tidak saling menghitung.

`tool_error_text` dipakai sebagai `handle_tool_errors` di `ToolNode` yang punya wrapper. Dengan
wrapper, `ToolNode` mengubah exception apa pun dari wrapper menjadi `ToolMessage` error tanpa
memeriksa tipenya, jadi bug di tool ikut tersembunyi. Handler ini hanya menerima `ToolException`
dan melempar ulang error lain.
"""

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Final

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import ToolException
from langgraph.prebuilt.tool_node import TOOL_CALL_ERROR_TEMPLATE, ToolCallRequest

from agent_service.core.constants import DEFAULT_TOOL_MAX_CONSECUTIVE_ERRORS
from agent_service.harness.offload import ToolExecutor, ToolResult

logger = logging.getLogger(__name__)

ERROR_STATUS: Final = "error"
MESSAGES_KEY: Final = "messages"
BLOCKED_TEXT: Final = (
    "{tool} failed {count} times in a row, so it was not run again. Do not call {tool} again "
    "in this turn. Explain the last error to the user and answer with what you already have."
)

type ToolCallWrapper = Callable[[ToolCallRequest, ToolExecutor], Awaitable[ToolResult]]


class ToolFailureGuard:
    """Menghentikan tool yang terus gagal di satu giliran.

    Class karena menyimpan batas dari `Settings` dan dipakai sebagai callable `awrap_tool_call`.
    """

    def __init__(self, max_consecutive_errors: int = DEFAULT_TOOL_MAX_CONSECUTIVE_ERRORS) -> None:
        """Inisialisasi guard.

        Args:
            max_consecutive_errors: Kegagalan beruntun sebelum tool tidak dijalankan lagi
                (`TOOL_MAX_CONSECUTIVE_ERRORS`).
        """
        self._max_errors = max_consecutive_errors

    @property
    def max_consecutive_errors(self) -> int:
        """Batas kegagalan beruntun per tool."""
        return self._max_errors

    async def __call__(self, request: ToolCallRequest, execute: ToolExecutor) -> ToolResult:
        """Jalankan tool, kecuali tool ini sudah gagal beruntun sebanyak batas di giliran ini."""
        tool_name = request.tool_call["name"]
        failures = consecutive_failures(_state_messages(request.state), tool_name)
        if failures < self._max_errors:
            return await execute(request)
        logger.info("Blocked %s after %d consecutive failures", tool_name, failures)
        return ToolMessage(
            content=BLOCKED_TEXT.format(tool=tool_name, count=failures),
            tool_call_id=request.tool_call["id"] or "",
            name=tool_name,
            status=ERROR_STATUS,
        )

    def around(self, inner: ToolCallWrapper | None) -> ToolCallWrapper:
        """Wrapper `awrap_tool_call` berisi guard ini di luar `inner` (misalnya offloader).

        Guard di luar, supaya tool yang diblokir tidak sampai ke wrapper lain.
        """
        if inner is None:
            return self

        async def guarded(request: ToolCallRequest, execute: ToolExecutor) -> ToolResult:
            async def run_inner(inner_request: ToolCallRequest) -> ToolResult:
                return await inner(inner_request, execute)

            return await self(request, run_inner)

        return guarded


def tool_error_text(error: ToolException) -> str:
    """Isi `ToolMessage` untuk `ToolException`. Error lain dilempar ulang supaya run gagal.

    Function, bukan class: konvensi `handle_tool_errors` milik `ToolNode`, yang juga membaca
    anotasi parameter ini untuk memilih exception yang ditangani.

    >>> tool_error_text(ToolException("service down")).splitlines()
    ["Error: ToolException('service down')", ' Please fix your mistakes.']
    >>> tool_error_text(RuntimeError("bug"))
    Traceback (most recent call last):
    RuntimeError: bug
    """
    if not isinstance(error, ToolException):
        raise error
    return TOOL_CALL_ERROR_TEMPLATE.format(error=repr(error))


def consecutive_failures(messages: Sequence[BaseMessage], tool_name: str) -> int:
    """Jumlah kegagalan beruntun terakhir `tool_name` sejak pesan human terakhir.

    Nama tool dibaca dari tool call `AIMessage`, karena `ToolMessage` yang dibuat tool sendiri
    tidak selalu membawa `name`. Hasil yang berhasil me-reset hitungan.

    >>> call = lambda i: AIMessage("", tool_calls=[{"name": "f", "args": {}, "id": i}])
    >>> fail = lambda i: ToolMessage("x", tool_call_id=i, status="error")
    >>> ok = lambda i: ToolMessage("y", tool_call_id=i)
    >>> turn = [HumanMessage("q"), call("1"), fail("1"), call("2"), ok("2"), call("3"), fail("3")]
    >>> consecutive_failures(turn, "f"), consecutive_failures(turn, "g")
    (1, 0)
    >>> consecutive_failures([call("1"), fail("1"), HumanMessage("again")], "f")
    0
    """
    turn = _current_turn(messages)
    names = _tool_call_names(turn)
    count = 0
    for message in turn:
        if not isinstance(message, ToolMessage):
            continue
        if names.get(message.tool_call_id, message.name) != tool_name:
            continue
        count = count + 1 if message.status == ERROR_STATUS else 0
    return count


def _current_turn(messages: Sequence[BaseMessage]) -> Sequence[BaseMessage]:
    """Message sejak pesan human terakhir (giliran yang sedang berjalan)."""
    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            return messages[index + 1 :]
    return messages


def _tool_call_names(messages: Sequence[BaseMessage]) -> dict[str, str]:
    """Peta ID tool call → nama tool dari setiap `AIMessage`."""
    names: dict[str, str] = {}
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls:
            if call["id"] is not None:
                names[call["id"]] = call["name"]
    return names


def _state_messages(state: object) -> Sequence[BaseMessage]:
    """Message dari state `ToolNode` (dict state graph, atau list message)."""
    messages = state.get(MESSAGES_KEY, []) if isinstance(state, Mapping) else state
    if not isinstance(messages, Sequence):
        return []
    return [message for message in messages if isinstance(message, BaseMessage)]
