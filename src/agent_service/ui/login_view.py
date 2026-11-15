"""Login dev console (FR-33): form username/password, logout, dan sesi kedaluwarsa.

Access token disimpan di `AgentClient` milik session browser, dan username di
`st.session_state`, bukan di URL. Jadi link ke percakapan tidak lagi memberi akses ke thread.
"""

import logging
from typing import Final

import streamlit as st

from agent_service.client import AgentClient, AgentClientError, ServiceUnreachableError

logger = logging.getLogger(__name__)

USERNAME_STATE_KEY: Final = "auth_username"
# State lain milik session user (percakapan, cache client) yang dihapus saat logout.
USER_STATE_KEYS: Final = ("chat_session",)
NOTICE_STATE_KEY: Final = "auth_notice"
LOGIN_FORM_KEY: Final = "login_form"
USERNAME_INPUT_KEY: Final = "login_username"
PASSWORD_INPUT_KEY: Final = "login_password"
LOGIN_HEADING: Final = "Sign in"
USERNAME_LABEL: Final = "Username"
PASSWORD_LABEL: Final = "Password"
LOGIN_BUTTON_LABEL: Final = "Sign in"
LOGOUT_LABEL: Final = ":material/logout: Sign out"
SIGNED_IN_TEMPLATE: Final = "Signed in as **{username}**"
LOGIN_HINT: Final = (
    "Accounts are created by an operator: "
    "`uv run python -m agent_service.manage create-user <username>`."
)
INVALID_LOGIN_TEXT: Final = "Invalid username or password."
LOGIN_FAILED_TEMPLATE: Final = "Sign-in failed: {error}"
UNREACHABLE_TEMPLATE: Final = "Cannot reach the agent service at {url}."
SESSION_EXPIRED_TEXT: Final = "Your session has expired. Please sign in again."
HTTP_UNAUTHORIZED: Final = 401
# Format username yang tidak valid dijawab 422, dan diperlakukan sama dengan login yang salah.
LOGIN_REJECTED_STATUSES: Final = (HTTP_UNAUTHORIZED, 422)


class LoginView:
    """Form login. Setelah berhasil, token dipasang di client dan script diulang."""

    def __init__(self, client: AgentClient) -> None:
        """Inisialisasi view.

        Args:
            client: Client milik session browser ini.
        """
        self._client = client

    def render(self) -> None:
        """Gambar form login, beserta pesan dari logout otomatis sebelumnya jika ada."""
        st.subheader(LOGIN_HEADING)
        notice = st.session_state.pop(NOTICE_STATE_KEY, None)
        if notice:
            st.info(notice)
        with st.form(LOGIN_FORM_KEY):
            username = st.text_input(USERNAME_LABEL, key=USERNAME_INPUT_KEY)
            password = st.text_input(PASSWORD_LABEL, type="password", key=PASSWORD_INPUT_KEY)
            submitted = st.form_submit_button(LOGIN_BUTTON_LABEL)
        st.caption(LOGIN_HINT)
        if submitted:
            self._log_in(username, password)

    def _log_in(self, username: str, password: str) -> None:
        """Kirim kredensial. Berhasil: simpan username dan ulang script. Gagal: tampilkan alasan."""
        try:
            token = self._client.login(username, password)
        except AgentClientError as error:
            logger.info("Sign-in failed: %s", error)
            st.error(self._error_text(error))
            return
        st.session_state[USERNAME_STATE_KEY] = token.username
        st.rerun()

    def _error_text(self, error: AgentClientError) -> str:
        """Pesan untuk user tanpa membedakan username yang tidak ada dan password yang salah."""
        if isinstance(error, ServiceUnreachableError):
            return UNREACHABLE_TEMPLATE.format(url=self._client.base_url)
        if error.status_code in LOGIN_REJECTED_STATUSES:
            return INVALID_LOGIN_TEXT
        return LOGIN_FAILED_TEMPLATE.format(error=error)


def signed_in_username() -> str | None:
    """Username yang sedang login di session browser ini."""
    username = st.session_state.get(USERNAME_STATE_KEY)
    return username if isinstance(username, str) else None


def log_out(client: AgentClient, notice: str | None = None) -> None:
    """Hapus token dan semua state milik user, supaya user berikutnya mulai bersih.

    Aman dipanggil sebagai callback widget (tanpa `st.rerun()`).

    Args:
        client: Client milik session browser ini.
        notice: Pesan yang ditampilkan di form login berikutnya.
    """
    client.set_access_token(None)
    st.session_state.pop(USERNAME_STATE_KEY, None)
    for key in USER_STATE_KEYS:
        st.session_state.pop(key, None)
    if notice is not None:
        st.session_state[NOTICE_STATE_KEY] = notice


def end_expired_session(client: AgentClient, error: AgentClientError) -> None:
    """Jika service menolak token (401), logout lalu ulang script ke form login.

    Untuk error lain fungsi ini tidak melakukan apa-apa, jadi pemanggil tetap menampilkannya.
    Jangan dipanggil dari callback widget, karena `st.rerun()` tidak berlaku di sana.
    """
    if error.status_code != HTTP_UNAUTHORIZED:
        return
    log_out(client, notice=SESSION_EXPIRED_TEXT)
    st.rerun()


def render_account(client: AgentClient, username: str) -> None:
    """Nama user yang login dan tombol logout, untuk sidebar."""
    st.caption(SIGNED_IN_TEMPLATE.format(username=username))
    st.button(LOGOUT_LABEL, on_click=log_out, args=(client,), key="sidebar_logout")
