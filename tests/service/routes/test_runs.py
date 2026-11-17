"""Acceptance F31 lewat API: setiap run menyimpan trace yang bisa dibaca pemiliknya."""

import uuid
from collections.abc import Callable
from typing import Any

import psycopg
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatResult
from langgraph.store.base import BaseStore
from sqlalchemy.exc import OperationalError

from agent_service.agents.base import AgentGraph, BaseAgent, Checkpointer
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.agents.tool_calling import ToolCallingAgent
from agent_service.agents.tools.calculator import calculator
from agent_service.harness.context import ContextBuilder
from agent_service.llm.fake import FakeModel
from agent_service.schema.responses import ChatMessage
from agent_service.schema.stream import STREAM_EVENT_ADAPTER, MessageEvent
from agent_service.schema.traces import RunTrace

type AuthHeaders = Callable[..., dict[str, str]]

USAGE = UsageMetadata(input_tokens=40, output_tokens=6, total_tokens=46)
CALCULATE = AIMessage(
    content="",
    tool_calls=[{"name": "calculator", "args": {"expression": "6*7"}, "id": "c1"}],
    usage_metadata=USAGE,
)
ANSWER = AIMessage(content="6 x 7 = 42", usage_metadata=USAGE)


class CalculatingAgent(ToolCallingAgent):
    """Agent dengan kalkulator dan model yang selalu menghitung dulu, dengan usage token."""

    def __init__(self) -> None:
        super().__init__("calc", "Calculates", [calculator], ContextBuilder())

    def build(
        self, model: BaseChatModel, checkpointer: Checkpointer, store: BaseStore | None = None
    ) -> AgentGraph:
        return super().build(FakeModel(responses=[CALCULATE, ANSWER]), checkpointer, store)


class BrokenModel(FakeModel):
    """Model yang selalu gagal, seperti provider yang mati."""

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> ChatResult:
        raise ConnectionError("model provider is down")


class BrokenAgent(ChatbotAgent):
    def __init__(self) -> None:
        super().__init__(agent_id="broken", description="Always fails")

    def build(
        self, model: BaseChatModel, checkpointer: Checkpointer, store: BaseStore | None = None
    ) -> AgentGraph:
        return super().build(BrokenModel(), checkpointer, store)


@pytest.fixture
def agents(interrupt_agent: BaseAgent) -> list[BaseAgent]:
    return [ChatbotAgent(), CalculatingAgent(), BrokenAgent(), interrupt_agent]


async def trace_of(client: AsyncClient, run_id: str | None) -> RunTrace:
    response = await client.get(f"/runs/{run_id}/trace")
    assert response.status_code == 200, response.text
    return RunTrace.model_validate(response.json())


async def test_invoke_run_has_model_and_tool_spans_with_tokens(client: AsyncClient) -> None:
    response = await client.post("/calc/invoke", json={"message": "6*7?"})
    reply = ChatMessage.model_validate(response.json())

    trace = await trace_of(client, reply.run_id)

    assert (trace.run_id, trace.agent_id, trace.status) == (reply.run_id, "calc", "ok")
    assert [(span.kind, span.name, span.status) for span in trace.spans] == [
        ("model", "FakeModel", "ok"),
        ("tool", "calculator", "ok"),
        ("model", "FakeModel", "ok"),
    ]
    assert (trace.input_tokens, trace.output_tokens) == (80, 12)
    assert trace.duration_ms >= max(span.duration_ms for span in trace.spans)


async def test_streamed_run_is_traced(client: AsyncClient) -> None:
    body = {"message": "Halo", "stream_tokens": True}
    async with client.stream("POST", "/chatbot/stream", json=body) as response:
        frames = [line async for line in response.aiter_lines() if line.startswith("data: {")]
    events = [STREAM_EVENT_ADAPTER.validate_json(frame.removeprefix("data: ")) for frame in frames]
    [message] = [event.content for event in events if isinstance(event, MessageEvent)]

    trace = await trace_of(client, message.run_id)

    assert (trace.agent_id, trace.status) == ("chatbot", "ok")
    assert [span.kind for span in trace.spans] == ["model"]


async def test_interrupted_run_is_marked_interrupted(client: AsyncClient) -> None:
    asked = await client.post("/interrupt/invoke", json={"message": "Hi"})

    trace = await trace_of(client, asked.json()["run_id"])

    assert trace.status == "interrupted"


async def test_failed_run_is_traced_with_its_error(client: AsyncClient, database_url: str) -> None:
    response = await client.post("/broken/invoke", json={"message": "Hi"})

    # Run gagal tidak mengembalikan run_id ke client, jadi trace dibaca langsung dari tabel.
    with psycopg.connect(database_url) as connection:
        rows = connection.execute(
            "SELECT status, error FROM run_traces WHERE kind = 'run' AND agent_id = 'broken'"
        ).fetchall()
    assert response.status_code == 500
    assert rows == [("error", "ConnectionError: model provider is down")]


async def test_trace_of_another_user_is_not_found(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    reply = (await client.post("/chatbot/invoke", json={"message": "Rahasia"})).json()

    other = await client.get(f"/runs/{reply['run_id']}/trace", headers=auth_headers("user-b"))
    unknown = await client.get(f"/runs/{uuid.uuid4()}/trace")
    invalid = await client.get("/runs/not-a-uuid/trace")

    assert other.status_code == 404
    assert unknown.status_code == 404
    assert invalid.status_code == 422


async def test_trace_failure_does_not_break_the_reply(
    app: FastAPI, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def database_down(*args: object) -> None:
        raise OperationalError("INSERT", {}, Exception("database is down"))

    monkeypatch.setattr(app.state.trace_repository, "add_spans", database_down)

    response = await client.post("/chatbot/invoke", json={"message": "Halo"})

    assert response.status_code == 200
    assert (await client.get(f"/runs/{response.json()['run_id']}/trace")).status_code == 404
