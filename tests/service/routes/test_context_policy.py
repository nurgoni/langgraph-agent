"""Acceptance F29 lewat API: riwayat diringkas untuk model, tetapi `/history` tetap lengkap."""

import pytest
from httpx import AsyncClient

from agent_service.agents.base import BaseAgent
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.harness.context_policy import ContextPolicy
from agent_service.llm.fake import DEFAULT_FAKE_RESPONSE
from agent_service.schema.responses import ChatHistory
from agent_service.schema.stream import STREAM_EVENT_ADAPTER, TokenEvent

BUDGET = 1000
THREAD_ID = "long-thread"
LONG_MESSAGE = "Tell me more about this, with every detail you know. " * 10  # ±130 token
TURNS = 10


@pytest.fixture
def agents() -> list[BaseAgent]:
    return [ChatbotAgent(context_policy=ContextPolicy(max_tokens=BUDGET))]


async def test_history_stays_complete_after_summarization(client: AsyncClient) -> None:
    for turn in range(TURNS):
        body = {"message": f"{turn}: {LONG_MESSAGE}", "thread_id": THREAD_ID}
        assert (await client.post("/invoke", json=body)).status_code == 200

    response = await client.post("/history", json={"thread_id": THREAD_ID})

    history = ChatHistory.model_validate(response.json())
    assert [message.type for message in history.messages] == ["human", "ai"] * TURNS
    assert history.messages[0].content.startswith("0: ")


async def test_summarization_tokens_are_not_streamed(client: AsyncClient) -> None:
    for turn in range(TURNS - 1):
        body = {"message": f"{turn}: {LONG_MESSAGE}", "thread_id": THREAD_ID}
        await client.post("/invoke", json=body)

    # Pesan besar memastikan giliran ini melewati anggaran dan memicu peringkasan.
    body = {"message": LONG_MESSAGE * 3, "thread_id": THREAD_ID, "stream_tokens": True}
    async with client.stream("POST", "/stream", json=body) as response:
        lines = [line async for line in response.aiter_lines() if line.startswith("data: {")]

    events = [STREAM_EVENT_ADAPTER.validate_json(line.removeprefix("data: ")) for line in lines]
    tokens = "".join(event.content for event in events if isinstance(event, TokenEvent))
    assert tokens == DEFAULT_FAKE_RESPONSE
