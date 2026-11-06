from streamlit.testing.v1 import AppTest

from agent_service.ui.url_state import UrlState

READ_SCRIPT = """
import streamlit as st
from agent_service.ui.url_state import UrlState

state = UrlState.read()
st.text(f"{state.user_id}|{state.thread_id}|{state.agent_id}")
"""

WRITE_SCRIPT = """
from agent_service.ui.url_state import UrlState

UrlState(user_id="u1", thread_id=None, agent_id="chatbot").write()
"""


def test_read_takes_values_from_query_params() -> None:
    app = AppTest.from_string(READ_SCRIPT, default_timeout=10)
    app.query_params.update({"user_id": "u1", "thread_id": "t1", "agent": "chatbot"})

    app.run()

    assert app.text[0].value == "u1|t1|chatbot"


def test_read_treats_missing_and_empty_params_as_none() -> None:
    app = AppTest.from_string(READ_SCRIPT, default_timeout=10)
    app.query_params["thread_id"] = ""

    app.run()

    assert app.text[0].value == "None|None|None"


def test_write_sets_filled_params_and_removes_empty_ones() -> None:
    app = AppTest.from_string(WRITE_SCRIPT, default_timeout=10)
    app.query_params.update({"thread_id": "old", "utm_source": "mail"})

    app.run()

    assert dict(app.query_params) == {"user_id": "u1", "agent": "chatbot", "utm_source": "mail"}


def test_as_params_skips_empty_values() -> None:
    assert UrlState(thread_id="t1").as_params() == {"thread_id": "t1"}
