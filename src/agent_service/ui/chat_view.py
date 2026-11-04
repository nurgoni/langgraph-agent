"""Area chat: riwayat, input user, dan jawaban agent yang di-stream (FR-20, FR-24)."""

import logging
from collections.abc import Callable
from typing import Final

import streamlit as st

from agent_service.client import (
    AgentClient,
    AgentClientError,
    ServiceUnreachableError,
    StreamRun,
)
from agent_service.schema.responses import ChatMessage
from agent_service.schema.stream import ErrorEvent, MessageEvent, StreamEvent, TokenEvent
from agent_service.ui.message_renderer import MessageRenderer
from agent_service.ui.session import ChatSession

logger = logging.getLogger(__name__)

CHAT_INPUT_PLACEHOLDER: Final = "Type a message…"
SERVICE_ERROR_TEMPLATE: Final = "Agent service error: {error}"
UNREACHABLE_TEMPLATE: Final = (
    "Cannot reach the agent service at {url}. Start it with "
    "`uv run python -m agent_service.run_service`, or set AGENT_URL to the running service."
)
THREAD_NOT_FOUND_TEMPLATE: Final = "Conversation {thread_id} was not found. Starting a new chat."
HTTP_NOT_FOUND: Final = 404


class ChatView:
    """Menggambar percakapan dan mengirim pesan baru lewat `AgentClient.stream`."""

    def __init__(
        self,
        client: AgentClient,
        session: ChatSession,
        on_thread_created: Callable[[], None] | None = None,
    ) -> None:
        """Inisialisasi view.

        Args:
            client: Client ke agent service.
            session: State percakapan browser ini.
            on_thread_created: Dipanggil saat service membuat thread baru, misalnya untuk
                menyegarkan daftar thread di sidebar.
        """
        self._client = client
        self._session = session
        self._on_thread_created = on_thread_created

    def render(self) -> None:
        """Gambar riwayat, lalu kirim pesan jika user baru saja mengetik."""
        self._ensure_history()
        history_renderer = MessageRenderer()
        for message in self._session.messages:
            history_renderer.render(message)
        prompt = st.chat_input(CHAT_INPUT_PLACEHOLDER)
        if prompt:
            self._send(prompt)

    def _send(self, prompt: str) -> None:
        """Tampilkan pesan user, lalu stream jawaban agent ke layar dan ke session.

        Jika run membuat thread baru dan selesai tanpa error, script diulang supaya sidebar langsung
        menampilkan thread tersebut. Saat ada error, script tidak diulang agar pesan error tetap
        terlihat.
        """
        renderer = MessageRenderer(live=True)
        human_message = ChatMessage(type="human", content=prompt)
        renderer.render(human_message)
        stream = self._client.stream(
            prompt,
            model=self._session.model,
            thread_id=self._session.thread_id,
            user_id=self._session.user_id,
            stream_tokens=self._session.stream_tokens,
        )
        created_thread = False
        failed = False
        try:
            with stream as run:
                created_thread = self._start_turn(run, human_message)
                for event in run:
                    failed = self._handle_event(event, renderer) or failed
        except AgentClientError as error:
            logger.warning("Agent request failed: %s", error)
            renderer.render_error(self._error_text(error))
            failed = True
        if created_thread:
            self._announce_new_thread(refresh_page=not failed)

    def _ensure_history(self) -> None:
        """Muat riwayat thread yang dibuka dari URL, sekali per session.

        Thread yang tidak ditemukan (atau milik user lain) diganti chat baru. Jika service tidak
        terjangkau, riwayat dicoba lagi pada run berikutnya.
        """
        thread_id = self._session.thread_id
        if self._session.history_loaded or thread_id is None:
            return
        try:
            history = self._client.get_history(thread_id, self._session.user_id)
        except AgentClientError as error:
            self._report_history_error(error, thread_id)
            return
        self._session.open_thread(thread_id, history.messages)

    def _report_history_error(self, error: AgentClientError, thread_id: str) -> None:
        """Tampilkan alasan riwayat gagal dimuat. Thread yang tidak ada diganti chat baru."""
        logger.warning("Loading history for %s failed: %s", thread_id, error)
        if error.status_code == HTTP_NOT_FOUND:
            st.warning(THREAD_NOT_FOUND_TEMPLATE.format(thread_id=thread_id))
            self._session.start_new_thread()
            return
        st.error(self._error_text(error))

    def _error_text(self, error: AgentClientError) -> str:
        """Pesan error untuk user, dengan petunjuk jika service tidak terjangkau."""
        if isinstance(error, ServiceUnreachableError):
            return UNREACHABLE_TEMPLATE.format(url=self._client.base_url)
        return SERVICE_ERROR_TEMPLATE.format(error=error)

    def _start_turn(self, run: StreamRun, human_message: ChatMessage) -> bool:
        """Simpan ID run dan pesan user, setelah service menerima request.

        Returns:
            `True` jika service membuat thread baru untuk run ini.
        """
        is_new_thread = run.thread_id != self._session.thread_id
        self._session.remember_run(run.thread_id, run.user_id)
        self._session.messages.append(human_message)
        return is_new_thread

    def _announce_new_thread(self, refresh_page: bool) -> None:
        """Beri tahu pemilik callback, lalu ulang script jika diminta."""
        if self._on_thread_created is not None:
            self._on_thread_created()
        if refresh_page:
            st.rerun()

    def _handle_event(self, event: StreamEvent, renderer: MessageRenderer) -> bool:
        """Teruskan satu event stream ke renderer, dan simpan message utuh ke session.

        Returns:
            `True` jika event berupa error dari service.
        """
        match event:
            case TokenEvent():
                renderer.append_token(event.content)
            case MessageEvent():
                renderer.render(event.content)
                self._session.messages.append(event.content)
            case ErrorEvent():
                renderer.render_error(event.content)
                return True
        return False
