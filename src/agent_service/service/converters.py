"""Transformasi murni dari objek agent/LangChain ke schema API.

Ditulis sebagai function karena tanpa state (AGENTS.md § Class vs Function). Letaknya di
`service/`, bukan `schema/`, supaya schema tidak bergantung pada agent maupun LangChain.
"""

import json
from collections.abc import Mapping
from typing import Any, Final

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.messages import ChatMessage as LangChainChatMessage
from langgraph.types import Interrupt

from agent_service.agents.base import BaseAgent
from agent_service.llm.reasoning import message_reasoning
from agent_service.schema.responses import AgentInfo, ChatMessage, ToolCall

CUSTOM_MESSAGE_ROLE: Final = "custom"
TEXT_BLOCK_TYPE: Final = "text"
INTERRUPT_KEY: Final = "__interrupt__"
MESSAGES_KEY: Final = "messages"


class UnsupportedMessageError(ValueError):
    """Message LangChain tidak punya padanan di `ChatMessage`."""


def agent_to_info(agent: BaseAgent) -> AgentInfo:
    """Ubah agent menjadi `AgentInfo`, termasuk JSON Schema `agent_config` (FR-27).

    Args:
        agent: Agent terdaftar.

    Returns:
        Informasi publik agent untuk `/info`.

    >>> from agent_service.agents.chatbot import ChatbotAgent
    >>> info = agent_to_info(ChatbotAgent())
    >>> info.key, info.config_schema["additionalProperties"]
    ('chatbot', False)
    """
    return AgentInfo(
        key=agent.agent_id,
        description=agent.description,
        config_schema=agent.config_schema.model_json_schema(),
    )


def content_to_text(content: str | list[str | dict[str, Any]]) -> str:  # Any: blok provider
    """Gabungkan konten message LangChain menjadi teks. Blok selain teks (gambar, tool_use) dibuang.

    >>> content_to_text(["Halo ", {"type": "text", "text": "dunia"}, {"type": "image_url"}])
    'Halo dunia'
    """
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif block.get("type") == TEXT_BLOCK_TYPE:
            parts.append(str(block.get("text", "")))
    return "".join(parts)


def langchain_to_chat_message(message: BaseMessage) -> ChatMessage:
    """Ubah message LangChain menjadi `ChatMessage`.

    Args:
        message: Message human, AI, tool, atau `ChatMessage` LangChain dengan role `custom`.

    Returns:
        Message dalam bentuk netral untuk API.

    Raises:
        UnsupportedMessageError: Untuk tipe message lain (misalnya `SystemMessage`).

    >>> langchain_to_chat_message(HumanMessage("Hai")).type
    'human'
    """
    match message:
        case HumanMessage():
            return ChatMessage(type="human", content=content_to_text(message.content))
        case AIMessage():
            return _ai_to_chat_message(message)
        case ToolMessage():
            return ChatMessage(
                type="tool",
                content=content_to_text(message.content),
                tool_call_id=message.tool_call_id,
            )
        case LangChainChatMessage() if message.role == CUSTOM_MESSAGE_ROLE:
            return _custom_to_chat_message(message)
        case _:
            raise UnsupportedMessageError(f"Unsupported message type: {type(message).__name__}")


def interrupt_to_chat_message(interrupt: Interrupt) -> ChatMessage:
    """Tampilkan pertanyaan interrupt sebagai message AI agar client bisa menjawabnya (FR-12).

    >>> interrupt_to_chat_message(Interrupt(value="Siapa namamu?")).content
    'Siapa namamu?'
    >>> interrupt_to_chat_message(Interrupt(value={"field": "nama"})).content
    '{"field": "nama"}'
    """
    value = interrupt.value
    content = value if isinstance(value, str) else json.dumps(value)
    return ChatMessage(type="ai", content=content)


def final_chat_message(state: Mapping[str, Any]) -> ChatMessage:  # Any: state per agent
    """Ambil jawaban akhir dari output `graph.ainvoke`: interrupt pertama, atau message terakhir.

    Args:
        state: Output graph dengan stream mode `values`.

    Returns:
        Message yang dikembalikan oleh `/invoke`.

    Raises:
        UnsupportedMessageError: Jika state tidak berisi message.
    """
    interrupts = state.get(INTERRUPT_KEY)
    if interrupts:
        return interrupt_to_chat_message(interrupts[0])
    messages = state.get(MESSAGES_KEY)
    if not messages:
        raise UnsupportedMessageError("Agent state has no messages")
    return langchain_to_chat_message(messages[-1])


def state_to_chat_messages(state: Mapping[str, Any]) -> list[ChatMessage]:  # Any: state per agent
    """Ubah channel `messages` dari state thread menjadi daftar `ChatMessage` (untuk history).

    >>> [m.type for m in state_to_chat_messages({"messages": [HumanMessage("Hai")]})]
    ['human']
    >>> state_to_chat_messages({})
    []
    """
    chat_messages: list[ChatMessage] = []
    for message in state.get(MESSAGES_KEY, []):
        chat_messages.append(langchain_to_chat_message(message))
    return chat_messages


def _ai_to_chat_message(message: AIMessage) -> ChatMessage:
    """Ubah `AIMessage`, termasuk tool call, metadata provider, dan reasoning model."""
    tool_calls: list[ToolCall] = []
    for tool_call in message.tool_calls:
        tool_calls.append(
            ToolCall(name=tool_call["name"], args=tool_call["args"], id=tool_call["id"])
        )
    return ChatMessage(
        type="ai",
        content=content_to_text(message.content),
        tool_calls=tool_calls,
        response_metadata=message.response_metadata,
        reasoning=message_reasoning(message) or None,
    )


def _custom_to_chat_message(message: LangChainChatMessage) -> ChatMessage:
    """Ubah message custom agent. Payload diambil dari blok dict pertama di konten.

    Raises:
        UnsupportedMessageError: Jika konten tidak berisi blok dict.
    """
    content = message.content
    if isinstance(content, list) and content and isinstance(content[0], dict):
        return ChatMessage(type="custom", content="", custom_data=content[0])
    raise UnsupportedMessageError("Custom message content must start with a dict payload")
