"""User, thread, dan agent di query param URL, supaya percakapan bisa dibuka ulang (FR-22).

`user_id` ikut disimpan karena service hanya membuka thread untuk pemiliknya. Siapa pun yang
memegang URL lengkap bisa membaca thread tersebut. Ini sesuai dengan v1 yang belum punya auth per
user.
"""

from dataclasses import dataclass
from typing import Final, Self

import streamlit as st

USER_ID_PARAM: Final = "user_id"
THREAD_ID_PARAM: Final = "thread_id"
AGENT_PARAM: Final = "agent"


@dataclass(frozen=True)
class UrlState:
    """Nilai query param milik UI. Param yang kosong berarti belum dipilih.

    >>> UrlState(user_id="u1", thread_id=None, agent_id="chatbot").as_params()
    {'user_id': 'u1', 'agent': 'chatbot'}
    """

    user_id: str | None = None
    thread_id: str | None = None
    agent_id: str | None = None

    @classmethod
    def read(cls) -> Self:
        """Baca state dari URL browser saat ini."""
        params = st.query_params
        return cls(
            user_id=params.get(USER_ID_PARAM) or None,
            thread_id=params.get(THREAD_ID_PARAM) or None,
            agent_id=params.get(AGENT_PARAM) or None,
        )

    def as_params(self) -> dict[str, str]:
        """Param yang terisi saja, siap ditulis ke URL."""
        params: dict[str, str] = {}
        if self.user_id is not None:
            params[USER_ID_PARAM] = self.user_id
        if self.thread_id is not None:
            params[THREAD_ID_PARAM] = self.thread_id
        if self.agent_id is not None:
            params[AGENT_PARAM] = self.agent_id
        return params

    def write(self) -> None:
        """Ganti query param milik UI di URL. Param lain dari URL dibiarkan."""
        params = st.query_params
        wanted = self.as_params()
        for name in (USER_ID_PARAM, THREAD_ID_PARAM, AGENT_PARAM):
            if name in wanted:
                params[name] = wanted[name]
            elif name in params:
                del params[name]
