import pytest
from pydantic import ValidationError

from agent_service.schema.requests import (
    THREADS_LIMIT_DEFAULT,
    THREADS_LIMIT_MAX,
    THREADS_LIMIT_MIN,
    TITLE_MAX_LENGTH,
    ChatHistoryInput,
    StreamInput,
    ThreadRenameInput,
    UserInput,
    UserThreadsQuery,
)


def test_user_input_defaults() -> None:
    user_input = UserInput(message="Halo")

    assert user_input.model is None
    assert user_input.thread_id is None
    assert user_input.user_id is None
    assert user_input.agent_config == {}


def test_agent_config_default_is_not_shared() -> None:
    first = UserInput(message="a")
    second = UserInput(message="b")

    first.agent_config["key"] = "value"

    assert second.agent_config == {}


def test_empty_message_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UserInput(message="")


@pytest.mark.parametrize("reserved_key", ["thread_id", "user_id", "model"])
def test_reserved_agent_config_key_is_rejected(reserved_key: str) -> None:
    with pytest.raises(ValidationError, match="reserved keys"):
        UserInput(message="Halo", agent_config={reserved_key: "x"})


def test_custom_agent_config_is_kept() -> None:
    user_input = UserInput(message="Halo", agent_config={"temperature": 0.2, "tags": ["a"]})

    assert user_input.agent_config == {"temperature": 0.2, "tags": ["a"]}


def test_stream_input_streams_tokens_by_default() -> None:
    assert StreamInput(message="Halo").stream_tokens is True


def test_chat_history_input_requires_user_id() -> None:
    with pytest.raises(ValidationError):
        ChatHistoryInput.model_validate({"thread_id": "t-1"})


def test_user_threads_query_uses_default_limit() -> None:
    assert UserThreadsQuery(user_id="u-1").limit == THREADS_LIMIT_DEFAULT


@pytest.mark.parametrize("limit", [THREADS_LIMIT_MIN - 1, THREADS_LIMIT_MAX + 1])
def test_user_threads_query_rejects_limit_out_of_range(limit: int) -> None:
    with pytest.raises(ValidationError):
        UserThreadsQuery(user_id="u-1", limit=limit)


def test_thread_title_is_stripped() -> None:
    rename = ThreadRenameInput(user_id="u-1", title="  Rencana liburan  ")

    assert rename.title == "Rencana liburan"


@pytest.mark.parametrize("title", ["   ", "x" * (TITLE_MAX_LENGTH + 1)])
def test_invalid_thread_title_is_rejected(title: str) -> None:
    with pytest.raises(ValidationError):
        ThreadRenameInput(user_id="u-1", title=title)
