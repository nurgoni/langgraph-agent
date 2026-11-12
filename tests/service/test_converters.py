import pytest
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages import ChatMessage as LangChainChatMessage
from langgraph.types import Interrupt
from pydantic import BaseModel

from agent_service.agents.base import EMPTY_CONFIG_DESCRIPTION
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.schema.responses import ChatMessage, ToolCall
from agent_service.service.converters import (
    UnsupportedMessageError,
    agent_to_info,
    final_chat_message,
    langchain_to_chat_message,
    state_to_chat_messages,
)


class LimitConfig(BaseModel):
    max_steps: int = 3


class LimitedAgent(ChatbotAgent):
    config_schema = LimitConfig


def test_agent_to_info_copies_identity() -> None:
    info = agent_to_info(ChatbotAgent(agent_id="bot", description="A bot"))

    assert (info.key, info.description) == ("bot", "A bot")


def test_default_config_schema_forbids_extra_keys() -> None:
    info = agent_to_info(ChatbotAgent())

    assert info.config_schema["additionalProperties"] is False
    assert info.config_schema.get("properties", {}) == {}


def test_custom_config_schema_is_exported_as_json_schema() -> None:
    info = agent_to_info(LimitedAgent())

    assert info.config_schema == LimitConfig.model_json_schema()


def test_default_config_schema_has_public_description() -> None:
    info = agent_to_info(ChatbotAgent())

    assert info.config_schema["description"] == EMPTY_CONFIG_DESCRIPTION


def test_human_message_is_converted() -> None:
    assert langchain_to_chat_message(HumanMessage("Hai")) == ChatMessage(
        type="human", content="Hai"
    )


def test_ai_message_keeps_tool_calls_and_metadata() -> None:
    message = AIMessage(
        content="",
        tool_calls=[{"name": "add", "args": {"a": 1}, "id": "call-1"}],
        response_metadata={"model_name": "gpt-test"},
    )

    chat_message = langchain_to_chat_message(message)

    assert chat_message.type == "ai"
    assert chat_message.tool_calls == [ToolCall(name="add", args={"a": 1}, id="call-1")]
    assert chat_message.response_metadata == {"model_name": "gpt-test"}


def test_ai_message_content_blocks_become_text() -> None:
    message = AIMessage(content=[{"type": "text", "text": "Halo"}, {"type": "tool_use", "id": "x"}])

    assert langchain_to_chat_message(message).content == "Halo"


def test_tool_message_keeps_tool_call_id() -> None:
    chat_message = langchain_to_chat_message(ToolMessage(content="3", tool_call_id="call-1"))

    assert (chat_message.type, chat_message.content, chat_message.tool_call_id) == (
        "tool",
        "3",
        "call-1",
    )


def test_custom_message_payload_becomes_custom_data() -> None:
    message = LangChainChatMessage(role="custom", content=[{"progress": 50}])

    chat_message = langchain_to_chat_message(message)

    assert (chat_message.type, chat_message.custom_data) == ("custom", {"progress": 50})


def test_custom_message_without_dict_payload_is_rejected() -> None:
    with pytest.raises(UnsupportedMessageError):
        langchain_to_chat_message(LangChainChatMessage(role="custom", content="text only"))


@pytest.mark.parametrize(
    "message",
    [SystemMessage("rules"), LangChainChatMessage(role="assistant", content="x")],
)
def test_unsupported_message_is_rejected(message: BaseMessage) -> None:
    with pytest.raises(UnsupportedMessageError):
        langchain_to_chat_message(message)


def test_final_message_prefers_interrupt() -> None:
    state = {"messages": [HumanMessage("hi")], "__interrupt__": [Interrupt(value="Nama?")]}

    assert final_chat_message(state) == ChatMessage(type="ai", content="Nama?")


def test_final_message_is_last_message() -> None:
    state = {"messages": [HumanMessage("hi"), AIMessage("halo")]}

    assert final_chat_message(state).content == "halo"


def test_final_message_requires_messages() -> None:
    with pytest.raises(UnsupportedMessageError):
        final_chat_message({"messages": []})


def test_state_messages_keep_order() -> None:
    state = {"messages": [HumanMessage("a"), AIMessage("b"), HumanMessage("c")]}

    assert [m.content for m in state_to_chat_messages(state)] == ["a", "b", "c"]


def test_ai_message_reasoning_is_converted() -> None:
    message = AIMessage(content="Hai", additional_kwargs={"reasoning_content": "Sapa balik"})

    assert langchain_to_chat_message(message).reasoning == "Sapa balik"


def test_ai_message_without_reasoning_has_none() -> None:
    assert langchain_to_chat_message(AIMessage(content="Hai")).reasoning is None


def test_subagent_marker_becomes_agent_field() -> None:
    marked = AIMessage(content="84", additional_kwargs={"subagent": "math_expert"})
    tool_result = ToolMessage(content="84", tool_call_id="c1", additional_kwargs={"subagent": "x"})

    assert langchain_to_chat_message(marked).agent == "math_expert"
    assert langchain_to_chat_message(tool_result).agent == "x"
    assert langchain_to_chat_message(AIMessage(content="Halo")).agent is None
