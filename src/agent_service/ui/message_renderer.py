"""Menggambar `ChatMessage` dan token stream ke halaman Streamlit (FR-20, FR-24)."""

import json
from collections.abc import Callable
from typing import Final, Literal

import streamlit as st
from streamlit.delta_generator import DeltaGenerator
from streamlit.elements.lib.mutable_status_container import StatusContainer

from agent_service.schema.responses import ChatMessage, MessageType, ToolCall

HUMAN_ROLE: Final = "human"
AI_ROLE: Final = "ai"
TOOL_LABEL_TEMPLATE: Final = ":material/build: Tool: {name}"
TOOL_INPUT_HEADING: Final = "Input"
TOOL_OUTPUT_HEADING: Final = "Output"
STREAMING_CURSOR: Final = "▌"

type StatusState = Literal["running", "complete", "error"]


class MessageRenderer:
    """Menggambar satu rangkaian message, untuk riwayat maupun run yang sedang berjalan.

    Class karena menyimpan state selama satu pass render: blok chat aktif (message AI, tool call,
    dan hasil tool berurutan digabung dalam satu blok), placeholder token yang sedang di-stream,
    dan status tool call yang menunggu hasilnya. Buat instance baru untuk setiap pass render.
    """

    def __init__(self, live: bool = False) -> None:
        """Inisialisasi renderer.

        Args:
            live: `True` untuk run yang sedang berjalan. Status tool call tampil "running"
                sampai hasilnya datang. `False` untuk riwayat, sehingga semua status langsung
                "complete".
        """
        self._live = live
        self._block_role: MessageType | None = None
        self._block: DeltaGenerator | None = None
        self._token_placeholder: DeltaGenerator | None = None
        self._streamed_text = ""
        self._pending_tools: dict[str, StatusContainer] = {}
        self._handlers: dict[MessageType, Callable[[ChatMessage], None]] = {
            "human": self._render_human,
            "ai": self._render_ai,
            "tool": self._render_tool_result,
            "custom": self._render_custom,
        }

    def render(self, message: ChatMessage) -> None:
        """Gambar satu message sesuai tipenya."""
        self._handlers[message.type](message)

    def append_token(self, text: str) -> None:
        """Tambahkan token ke jawaban AI yang sedang di-stream."""
        if self._token_placeholder is None:
            self._token_placeholder = self._block_for(AI_ROLE).empty()
        self._streamed_text += text
        self._token_placeholder.markdown(self._streamed_text + STREAMING_CURSOR)

    def render_error(self, text: str) -> None:
        """Tampilkan error dari run, dan tandai tool call yang belum selesai sebagai gagal."""
        for status in self._pending_tools.values():
            status.update(state="error")
        self._pending_tools.clear()
        self._block_for(AI_ROLE).error(text)

    def _render_human(self, message: ChatMessage) -> None:
        """Pesan user selalu membuka blok baru."""
        self._block = st.chat_message(HUMAN_ROLE)
        self._block_role = HUMAN_ROLE
        self._block.markdown(message.content)

    def _render_ai(self, message: ChatMessage) -> None:
        """Jawaban AI (menggantikan token yang di-stream) beserta tool call-nya."""
        block = self._block_for(AI_ROLE)
        if self._token_placeholder is not None:
            self._token_placeholder.markdown(message.content)
            self._token_placeholder = None
            self._streamed_text = ""
        elif message.content:
            block.markdown(message.content)
        for tool_call in message.tool_calls:
            self._open_tool_status(block, tool_call)

    def _render_tool_result(self, message: ChatMessage) -> None:
        """Isi status tool call yang cocok dengan `tool_call_id`, atau buat status baru."""
        status = self._pending_tools.pop(message.tool_call_id or "", None)
        if status is None:
            status = self._block_for(AI_ROLE).status(
                TOOL_LABEL_TEMPLATE.format(name="result"), state="complete"
            )
        status.markdown(f"**{TOOL_OUTPUT_HEADING}**")
        status.code(message.content)
        status.update(state="complete")

    def _render_custom(self, message: ChatMessage) -> None:
        """Event custom agent ditampilkan sebagai JSON di blok AI."""
        self._block_for(AI_ROLE).json(message.custom_data)

    def _open_tool_status(self, block: DeltaGenerator, tool_call: ToolCall) -> None:
        """Buat status yang bisa di-expand untuk satu tool call, berisi input-nya."""
        state: StatusState = "running" if self._live else "complete"
        status = block.status(TOOL_LABEL_TEMPLATE.format(name=tool_call.name), state=state)
        status.markdown(f"**{TOOL_INPUT_HEADING}**")
        status.code(json.dumps(tool_call.args, indent=2), language="json")
        if tool_call.id is not None:
            self._pending_tools[tool_call.id] = status

    def _block_for(self, role: MessageType) -> DeltaGenerator:
        """Blok chat untuk `role`, memakai ulang blok aktif jika perannya sama."""
        if self._block is None or self._block_role != role:
            self._block = st.chat_message(role)
            self._block_role = role
        return self._block


if __name__ == "__main__":
    # Demo: uv run streamlit run src/agent_service/ui/message_renderer.py
    demo = MessageRenderer()
    demo.render(ChatMessage(type="human", content="Berapa 12 * 7?"))
    demo.render(
        ChatMessage(
            type="ai",
            content="",
            tool_calls=[ToolCall(name="calculator", args={"expression": "12 * 7"}, id="c1")],
        )
    )
    demo.render(ChatMessage(type="tool", content="84", tool_call_id="c1"))
    demo.render(ChatMessage(type="ai", content="Hasilnya 84."))
