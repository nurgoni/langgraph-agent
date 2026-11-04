"""Sidebar: chat baru, pemilih agent dan model, dan toggle streaming (FR-21)."""

import logging
from typing import Final

import streamlit as st

from agent_service.client import AgentClient, AgentClientError
from agent_service.schema.responses import ServiceMetadata
from agent_service.ui.session import ChatSession

logger = logging.getLogger(__name__)

NEW_CHAT_LABEL: Final = ":material/add: New chat"
AGENT_LABEL: Final = "Agent"
MODEL_LABEL: Final = "Model"
STREAM_LABEL: Final = "Stream tokens"
INFO_UNAVAILABLE_TEMPLATE: Final = "Agent service unavailable: {error}"
UNKNOWN_AGENT_TEMPLATE: Final = "Agent {agent_id!r} is not available. Using {default!r} instead."
NEW_CHAT_KEY: Final = "sidebar_new_chat"
AGENT_KEY: Final = "sidebar_agent"
MODEL_KEY: Final = "sidebar_model"
STREAM_KEY: Final = "sidebar_stream_tokens"
FULL_WIDTH: Final = "stretch"


class SidebarView:
    """Menggambar sidebar dan menyimpan pilihan user ke `ChatSession` lewat callback widget.

    Callback dijalankan Streamlit sebelum script diulang, jadi pilihan baru sudah berlaku di run
    berikutnya tanpa `st.rerun()`.
    """

    def __init__(self, client: AgentClient, session: ChatSession) -> None:
        """Inisialisasi view.

        Args:
            client: Client ke agent service, untuk `/info`.
            session: State percakapan browser ini.
        """
        self._client = client
        self._session = session

    def render(self) -> None:
        """Gambar isi sidebar. Pemilih disembunyikan jika `/info` tidak bisa diambil."""
        with st.sidebar:
            st.button(
                NEW_CHAT_LABEL,
                key=NEW_CHAT_KEY,
                on_click=self._session.start_new_thread,
                width=FULL_WIDTH,
            )
            info = self._load_info()
            if info is not None:
                self._render_agent_picker(info)
                self._render_model_picker(info)
            st.toggle(
                STREAM_LABEL,
                value=self._session.stream_tokens,
                key=STREAM_KEY,
                on_change=self._on_stream_change,
            )

    def _load_info(self) -> ServiceMetadata | None:
        """Agent dan model dari service, atau `None` beserta pesan jika gagal."""
        try:
            return self._client.get_info()
        except AgentClientError as error:
            logger.warning("Loading service info failed: %s", error)
            st.caption(INFO_UNAVAILABLE_TEMPLATE.format(error=error))
            return None

    def _render_agent_picker(self, info: ServiceMetadata) -> None:
        """Pilihan agent. Agent dari URL yang tidak dikenal diganti agent default."""
        agent_ids = [agent.key for agent in info.agents]
        selected = self._session.agent_id
        if selected is not None and selected not in agent_ids:
            st.warning(UNKNOWN_AGENT_TEMPLATE.format(agent_id=selected, default=info.default_agent))
            self._session.switch_agent(None)
            selected = None
        current = info.default_agent if selected is None else selected
        st.selectbox(
            AGENT_LABEL,
            agent_ids,
            index=agent_ids.index(current),
            key=AGENT_KEY,
            on_change=self._on_agent_change,
        )
        for agent in info.agents:
            if agent.key == current:
                st.caption(agent.description)

    def _render_model_picker(self, info: ServiceMetadata) -> None:
        """Pilihan model dari allowlist service."""
        current = info.default_model if self._session.model is None else self._session.model
        index = info.models.index(current) if current in info.models else 0
        st.selectbox(
            MODEL_LABEL, info.models, index=index, key=MODEL_KEY, on_change=self._on_model_change
        )

    def _on_agent_change(self) -> None:
        """Agent baru berarti thread baru, karena thread terikat pada agent yang membuatnya."""
        self._session.switch_agent(st.session_state[AGENT_KEY])

    def _on_model_change(self) -> None:
        """Model dipakai mulai pesan berikutnya, di thread yang sama."""
        self._session.model = st.session_state[MODEL_KEY]

    def _on_stream_change(self) -> None:
        """Matikan atau nyalakan frame token. Tool call tetap tampil saat token dimatikan."""
        self._session.stream_tokens = st.session_state[STREAM_KEY]
