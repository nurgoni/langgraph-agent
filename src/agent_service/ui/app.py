"""Entrypoint UI: `uv run streamlit run src/agent_service/ui/app.py`."""

from typing import Final

import streamlit as st

from agent_service.client import AgentClient
from agent_service.ui.chat_view import ChatView
from agent_service.ui.session import ChatSession
from agent_service.ui.settings import UiSettings
from agent_service.ui.sidebar_view import SidebarView, clear_thread_list_cache

APP_TITLE: Final = "Agent Service"
APP_ICON: Final = ":material/smart_toy:"
# Test menaruh AgentClient (dengan transport tiruan) di key ini sebelum script dijalankan.
CLIENT_OVERRIDE_KEY: Final = "agent_client_override"
CLIENT_STATE_KEY: Final = "agent_client"


def resolve_client(settings: UiSettings) -> AgentClient:
    """Client milik session browser ini, dibuat sekali lalu dipakai ulang di setiap run.

    Satu client per session, bukan satu untuk semua session, karena `agent_id` client mengikuti
    pilihan agent masing-masing browser. Test bisa menaruh client sendiri di
    `CLIENT_OVERRIDE_KEY`.
    """
    for key in (CLIENT_OVERRIDE_KEY, CLIENT_STATE_KEY):
        client = st.session_state.get(key)
        if isinstance(client, AgentClient):
            return client
    client = AgentClient(
        base_url=settings.agent_url,
        auth_secret=settings.auth_token(),
        timeout=settings.request_timeout_seconds,
    )
    st.session_state[CLIENT_STATE_KEY] = client
    return client


def main() -> None:
    """Susun halaman. Dipanggil Streamlit setiap kali script dijalankan ulang.

    Function, bukan class: entrypoint script Streamlit.
    """
    st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON)
    settings = UiSettings()
    client = resolve_client(settings)
    session = ChatSession.current()
    st.title(APP_TITLE)
    # SidebarView juga menyelaraskan `client.agent_id` dengan agent terpilih.
    SidebarView(client, session).render()
    ChatView(client, session, on_thread_created=clear_thread_list_cache).render()
    session.to_url().write()


if __name__ == "__main__":
    main()
