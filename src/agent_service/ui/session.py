"""State percakapan per session browser, disimpan bertipe di `st.session_state`."""

from dataclasses import dataclass, field
from typing import Final, Self

import streamlit as st

from agent_service.schema.responses import ChatMessage

SESSION_STATE_KEY: Final = "chat_session"


@dataclass
class ChatSession:
    """Thread aktif dan message yang sudah tampil di layar.

    `thread_id` dan `user_id` kosong sampai run pertama. Setelah itu nilainya diambil dari header
    respons service, supaya giliran berikutnya melanjutkan thread yang sama.

    >>> session = ChatSession()
    >>> session.remember_run("t1", "u1")
    >>> session.thread_id, session.user_id
    ('t1', 'u1')
    """

    thread_id: str | None = None
    user_id: str | None = None
    messages: list[ChatMessage] = field(default_factory=list)

    @classmethod
    def current(cls) -> Self:
        """Session milik browser ini, dibuat saat pertama kali dibutuhkan."""
        session = st.session_state.get(SESSION_STATE_KEY)
        if not isinstance(session, cls):
            session = cls()
            st.session_state[SESSION_STATE_KEY] = session
        return session

    def remember_run(self, thread_id: str, user_id: str) -> None:
        """Simpan ID yang dipakai service untuk run terakhir."""
        self.thread_id = thread_id
        self.user_id = user_id
