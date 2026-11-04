"""Entrypoint UI: `uv run streamlit run src/agent_service/ui/app.py`."""

from typing import Final

import streamlit as st

from agent_service.client import AgentClient
from agent_service.ui.chat_view import ChatView
from agent_service.ui.session import ChatSession
from agent_service.ui.settings import UiSettings

APP_TITLE: Final = "Agent Service"
APP_ICON: Final = ":material/smart_toy:"
# Test menaruh AgentClient (dengan transport tiruan) di key ini sebelum script dijalankan.
CLIENT_OVERRIDE_KEY: Final = "agent_client_override"


@st.cache_resource(show_spinner=False)
def create_client(agent_url: str, auth_token: str | None, timeout: float) -> AgentClient:
    """Buat satu `AgentClient` per konfigurasi, dipakai bersama semua session browser.

    Function, bukan class: resource factory yang di-cache Streamlit.
    """
    return AgentClient(base_url=agent_url, auth_secret=auth_token, timeout=timeout)


def resolve_client(settings: UiSettings) -> AgentClient:
    """Client untuk run ini: override dari test jika ada, selain itu client yang di-cache."""
    override = st.session_state.get(CLIENT_OVERRIDE_KEY)
    if isinstance(override, AgentClient):
        return override
    return create_client(
        settings.agent_url, settings.auth_token(), settings.request_timeout_seconds
    )


def main() -> None:
    """Susun halaman. Dipanggil Streamlit setiap kali script dijalankan ulang.

    Function, bukan class: entrypoint script Streamlit.
    """
    st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON)
    settings = UiSettings()
    client = resolve_client(settings)
    st.title(APP_TITLE)
    ChatView(client, ChatSession.current()).render()


if __name__ == "__main__":
    main()
