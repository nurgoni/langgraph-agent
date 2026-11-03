from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agent_service.schema.responses import (
    AgentInfo,
    ChatHistory,
    ChatMessage,
    ServiceMetadata,
    ThreadSummary,
    ToolCall,
    UserThreads,
)


def test_chat_message_defaults_are_empty_and_not_shared() -> None:
    first = ChatMessage(type="ai", content="a")
    second = ChatMessage(type="ai", content="b")

    first.custom_data["key"] = "value"

    assert second.custom_data == {}
    assert second.tool_calls == []
    assert second.response_metadata == {}


def test_unknown_message_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ChatMessage.model_validate({"type": "system", "content": "x"})


def test_chat_message_round_trips_through_json() -> None:
    message = ChatMessage(
        type="ai",
        content="",
        tool_calls=[ToolCall(name="calculator", args={"expression": "1 + 1"}, id="call-1")],
        run_id="run-1",
    )

    restored = ChatMessage.model_validate_json(message.model_dump_json())

    assert restored == message


def test_chat_history_keeps_message_order() -> None:
    history = ChatHistory(
        messages=[ChatMessage(type="human", content="1"), ChatMessage(type="ai", content="2")]
    )

    assert [message.content for message in history.messages] == ["1", "2"]


def test_thread_summary_serializes_timestamp_as_iso() -> None:
    summary = ThreadSummary(
        thread_id="t-1",
        agent_id="chatbot",
        title="Halo",
        updated_at=datetime(2026, 11, 3, 10, 0, tzinfo=UTC),
    )

    payload = UserThreads(threads=[summary]).model_dump(mode="json")

    assert payload["threads"][0]["updated_at"] == "2026-11-03T10:00:00Z"


def test_service_metadata_exposes_agent_config_schema() -> None:
    agent = AgentInfo(
        key="chatbot",
        description="Chat sederhana",
        config_schema={"type": "object", "properties": {}},
    )

    metadata = ServiceMetadata(
        agents=[agent],
        models=["fake"],
        default_agent="chatbot",
        default_model="fake",
    )

    assert metadata.model_dump()["agents"][0]["config_schema"]["type"] == "object"
