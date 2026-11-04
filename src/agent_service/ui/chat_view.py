"""Area chat: riwayat, input user, dan jawaban agent yang di-stream (FR-20, FR-24)."""

import logging
from typing import Final

import streamlit as st

from agent_service.client import AgentClient, AgentClientError, StreamRun
from agent_service.schema.responses import ChatMessage
from agent_service.schema.stream import ErrorEvent, MessageEvent, StreamEvent, TokenEvent
from agent_service.ui.message_renderer import MessageRenderer
from agent_service.ui.session import ChatSession

logger = logging.getLogger(__name__)

CHAT_INPUT_PLACEHOLDER: Final = "Type a message…"
SERVICE_ERROR_TEMPLATE: Final = "Agent service error: {error}"


class ChatView:
    """Menggambar percakapan dan mengirim pesan baru lewat `AgentClient.stream`."""

    def __init__(self, client: AgentClient, session: ChatSession) -> None:
        """Inisialisasi view.

        Args:
            client: Client ke agent service.
            session: State percakapan browser ini.
        """
        self._client = client
        self._session = session

    def render(self) -> None:
        """Gambar riwayat, lalu kirim pesan jika user baru saja mengetik."""
        history_renderer = MessageRenderer()
        for message in self._session.messages:
            history_renderer.render(message)
        prompt = st.chat_input(CHAT_INPUT_PLACEHOLDER)
        if prompt:
            self._send(prompt)

    def _send(self, prompt: str) -> None:
        """Tampilkan pesan user, lalu stream jawaban agent ke layar dan ke session."""
        renderer = MessageRenderer(live=True)
        human_message = ChatMessage(type="human", content=prompt)
        renderer.render(human_message)
        stream = self._client.stream(
            prompt, thread_id=self._session.thread_id, user_id=self._session.user_id
        )
        try:
            with stream as run:
                self._start_turn(run, human_message)
                for event in run:
                    self._handle_event(event, renderer)
        except AgentClientError as error:
            logger.warning("Agent request failed: %s", error)
            renderer.render_error(SERVICE_ERROR_TEMPLATE.format(error=error))

    def _start_turn(self, run: StreamRun, human_message: ChatMessage) -> None:
        """Simpan ID run dan pesan user, setelah service menerima request."""
        self._session.remember_run(run.thread_id, run.user_id)
        self._session.messages.append(human_message)

    def _handle_event(self, event: StreamEvent, renderer: MessageRenderer) -> None:
        """Teruskan satu event stream ke renderer, dan simpan message utuh ke session."""
        match event:
            case TokenEvent():
                renderer.append_token(event.content)
            case MessageEvent():
                renderer.render(event.content)
                self._session.messages.append(event.content)
            case ErrorEvent():
                renderer.render_error(event.content)
