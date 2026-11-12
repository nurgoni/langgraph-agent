"""InterruptAgent lewat endpoint asli: pertanyaan interrupt, resume, dan riwayat (FR-12, FR-24)."""

from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from agent_service.agents.base import AgentGraph, Checkpointer
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.agents.interrupt import InterruptAgent
from agent_service.core.settings import Settings
from agent_service.llm.fake import FakeModel
from agent_service.schema.stream import STREAM_EVENT_ADAPTER, MessageEvent, TokenEvent
from agent_service.service.app import create_app

OWNER = "user-a"
QUESTION = "Kapan tanggal lahirmu?"


def extraction(birthdate: str | None) -> AIMessage:
    args = {"birthdate": birthdate, "follow_up_question": QUESTION}
    return AIMessage(
        content="", tool_calls=[{"name": "BirthdateExtraction", "args": args, "id": "x"}]
    )


class ScriptedInterruptAgent(InterruptAgent):
    """InterruptAgent dengan model tiruan yang sudah di-script, apa pun model dari request."""

    def build(self, model: BaseChatModel, checkpointer: Checkpointer) -> AgentGraph:
        scripted = FakeModel(
            responses=[extraction(None), extraction("1990-05-17"), "Zodiakmu Taurus!"]
        )
        return super().build(scripted, checkpointer)


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    settings = Settings(_env_file=None, use_fake_model=True, sqlite_db_path=tmp_path / "i.db")
    agents = [ChatbotAgent(), ScriptedInterruptAgent(today=lambda: date(2026, 11, 12))]
    app = create_app(settings, agents=agents)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
            yield http_client


async def invoke(client: AsyncClient, message: str) -> dict[str, Any]:  # Any: body JSON
    body = {"message": message, "thread_id": "t1", "user_id": OWNER}
    response = await client.post("/interrupt-agent/invoke", json=body)
    assert response.status_code == 200, response.text
    return response.json()


async def test_interrupt_and_resume_through_invoke(client: AsyncClient) -> None:
    question = await invoke(client, "Apa zodiakku?")
    answer = await invoke(client, "17 Mei 1990")

    assert (question["type"], question["content"]) == ("ai", QUESTION)
    assert answer["content"] == "Zodiakmu Taurus!"


async def test_history_keeps_question_flow_without_extraction_calls(client: AsyncClient) -> None:
    await invoke(client, "Apa zodiakku?")
    await invoke(client, "17 Mei 1990")

    response = await client.post(
        "/interrupt-agent/history", json={"thread_id": "t1", "user_id": OWNER}
    )

    messages = response.json()["messages"]
    assert [(m["type"], m["content"]) for m in messages] == [
        ("human", "Apa zodiakku?"),
        ("human", "17 Mei 1990"),
        ("ai", "Zodiakmu Taurus!"),
    ]


async def test_interrupt_and_resume_through_stream(client: AsyncClient) -> None:
    async def stream(message: str) -> list[object]:
        body = {"message": message, "thread_id": "t2", "user_id": OWNER}
        async with client.stream("POST", "/interrupt-agent/stream", json=body) as response:
            lines = [line async for line in response.aiter_lines() if line]
        assert lines[-1] == "data: [DONE]"
        return [STREAM_EVENT_ADAPTER.validate_json(line[6:]) for line in lines[:-1]]

    asked = await stream("Apa zodiakku?")
    answered = await stream("17 Mei 1990")

    assert [e.content.content for e in asked if isinstance(e, MessageEvent)] == [QUESTION]
    assert not any(isinstance(e, TokenEvent) for e in asked)
    tokens = "".join(e.content for e in answered if isinstance(e, TokenEvent))
    assert tokens == "Zodiakmu Taurus!"
