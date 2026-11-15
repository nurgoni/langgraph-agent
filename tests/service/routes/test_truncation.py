"""Acceptance F21: jawaban yang berhenti karena batas token ditandai `truncated` di semua jalur."""

import pytest
from httpx import AsyncClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from agent_service.agents.base import AgentGraph, BaseAgent, Checkpointer
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.llm.fake import FakeModel
from agent_service.schema.responses import ChatHistory, ChatMessage
from agent_service.schema.stream import STREAM_EVENT_ADAPTER, MessageEvent

OWNER = "user-a"
AGENT_PATH = "/truncating"
PARTIAL_ANSWER = "Jawaban ini terpo"


class TruncatingAgent(ChatbotAgent):
    """Chatbot yang modelnya selalu berhenti karena batas token (`finish_reason="length"`)."""

    def build(self, model: BaseChatModel, checkpointer: Checkpointer) -> AgentGraph:
        truncating_model = FakeModel(
            responses=[
                AIMessage(content=PARTIAL_ANSWER, response_metadata={"finish_reason": "length"})
            ]
        )
        return super().build(truncating_model, checkpointer)


@pytest.fixture
def agents() -> list[BaseAgent]:
    return [ChatbotAgent(), TruncatingAgent(agent_id="truncating", description="Truncates")]


async def test_invoke_marks_truncated_answer(client: AsyncClient) -> None:
    response = await client.post(f"{AGENT_PATH}/invoke", json={"message": "Halo"})

    assert response.status_code == 200, response.text
    message = ChatMessage.model_validate(response.json())
    assert message.content == PARTIAL_ANSWER
    assert message.truncated is True


async def test_stream_message_frame_marks_truncated_answer(client: AsyncClient) -> None:
    async with client.stream("POST", f"{AGENT_PATH}/stream", json={"message": "Halo"}) as response:
        assert response.status_code == 200
        lines = [line async for line in response.aiter_lines() if line.startswith("data: {")]

    events = [STREAM_EVENT_ADAPTER.validate_json(line.removeprefix("data: ")) for line in lines]
    messages = [event.content for event in events if isinstance(event, MessageEvent)]
    assert [(m.content, m.truncated) for m in messages] == [(PARTIAL_ANSWER, True)]


async def test_history_keeps_truncated_flag(client: AsyncClient) -> None:
    body = {"message": "Halo", "thread_id": "t1", "user_id": OWNER}
    await client.post(f"{AGENT_PATH}/invoke", json=body)

    response = await client.post(
        f"{AGENT_PATH}/history", json={"thread_id": "t1", "user_id": OWNER}
    )

    history = ChatHistory.model_validate(response.json())
    assert [(m.type, m.truncated) for m in history.messages] == [("human", False), ("ai", True)]


async def test_normal_answer_is_not_truncated(client: AsyncClient) -> None:
    response = await client.post("/chatbot/invoke", json={"message": "Halo"})

    assert ChatMessage.model_validate(response.json()).truncated is False
