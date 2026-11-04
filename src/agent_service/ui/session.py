"""State percakapan per session browser, disimpan bertipe di `st.session_state`."""

from dataclasses import dataclass, field
from typing import Final, Self
from uuid import uuid4

import streamlit as st

from agent_service.schema.responses import ChatMessage
from agent_service.ui.url_state import UrlState

SESSION_STATE_KEY: Final = "chat_session"


@dataclass
class ChatSession:
    """User, thread aktif, dan message yang sudah tampil di layar.

    `user_id` selalu ada (dari URL atau UUID baru) supaya daftar thread dan link bisa dibuka ulang.
    `thread_id` kosong sampai run pertama, lalu diambil dari header respons service.
    `history_loaded` bernilai `False` jika thread dibuka dari URL dan riwayatnya belum dimuat.

    >>> session = ChatSession(user_id="u1")
    >>> session.remember_run("t1", "u1")
    >>> session.to_url()
    UrlState(user_id='u1', thread_id='t1', agent_id=None)
    """

    user_id: str
    thread_id: str | None = None
    agent_id: str | None = None
    messages: list[ChatMessage] = field(default_factory=list)
    history_loaded: bool = True

    @classmethod
    def current(cls) -> Self:
        """Session milik browser ini, dibuat dari URL saat pertama kali dibutuhkan."""
        session = st.session_state.get(SESSION_STATE_KEY)
        if not isinstance(session, cls):
            session = cls.from_url(UrlState.read())
            st.session_state[SESSION_STATE_KEY] = session
        return session

    @classmethod
    def from_url(cls, url: UrlState) -> Self:
        """Session baru dari query param. Riwayat thread di URL dimuat belakangan.

        >>> ChatSession.from_url(UrlState(user_id="u1", thread_id="t1")).history_loaded
        False
        """
        return cls(
            user_id=url.user_id or str(uuid4()),
            thread_id=url.thread_id,
            agent_id=url.agent_id,
            history_loaded=url.thread_id is None,
        )

    def to_url(self) -> UrlState:
        """State yang ditulis ke URL setelah setiap run."""
        return UrlState(user_id=self.user_id, thread_id=self.thread_id, agent_id=self.agent_id)

    def remember_run(self, thread_id: str, user_id: str) -> None:
        """Simpan ID yang dipakai service untuk run terakhir."""
        self.thread_id = thread_id
        self.user_id = user_id

    def open_thread(self, thread_id: str, messages: list[ChatMessage]) -> None:
        """Tampilkan thread lain beserta riwayatnya."""
        self.thread_id = thread_id
        self.messages = messages
        self.history_loaded = True

    def start_new_thread(self) -> None:
        """Kosongkan layar. Thread baru dibuat service saat pesan pertama dikirim."""
        self.thread_id = None
        self.messages = []
        self.history_loaded = True
