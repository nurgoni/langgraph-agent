"""Thread dan agent di query param URL, supaya percakapan bisa dibuka ulang (FR-22).

Identitas user tidak lagi ada di URL (FR-33): service membuka thread hanya untuk pemegang access
token yang membuatnya, jadi URL yang dibagikan tidak memberi akses ke thread orang lain.
"""

from dataclasses import dataclass
from typing import Final, Self

import streamlit as st

THREAD_ID_PARAM: Final = "thread_id"
AGENT_PARAM: Final = "agent"
# Param dari versi sebelum login per user. Dihapus dari URL saat state ditulis.
LEGACY_USER_ID_PARAM: Final = "user_id"
MANAGED_PARAMS: Final = (THREAD_ID_PARAM, AGENT_PARAM, LEGACY_USER_ID_PARAM)


@dataclass(frozen=True)
class UrlState:
    """Nilai query param milik UI. Param yang kosong berarti belum dipilih.

    >>> UrlState(thread_id=None, agent_id="chatbot").as_params()
    {'agent': 'chatbot'}
    """

    thread_id: str | None = None
    agent_id: str | None = None

    @classmethod
    def read(cls) -> Self:
        """Baca state dari URL browser saat ini."""
        params = st.query_params
        return cls(
            thread_id=params.get(THREAD_ID_PARAM) or None,
            agent_id=params.get(AGENT_PARAM) or None,
        )

    def as_params(self) -> dict[str, str]:
        """Param yang terisi saja, siap ditulis ke URL."""
        params: dict[str, str] = {}
        if self.thread_id is not None:
            params[THREAD_ID_PARAM] = self.thread_id
        if self.agent_id is not None:
            params[AGENT_PARAM] = self.agent_id
        return params

    def write(self) -> None:
        """Ganti query param milik UI di URL. Param lain dari URL dibiarkan."""
        params = st.query_params
        wanted = self.as_params()
        for name in MANAGED_PARAMS:
            if name in wanted:
                params[name] = wanted[name]
            elif name in params:
                del params[name]
