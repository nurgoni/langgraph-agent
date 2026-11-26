"""Batas langkah run lewat API (FR-59, F47): `AGENT_RECURSION_LIMIT` dari `Settings`."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.managed import RemainingSteps
from langgraph.store.base import BaseStore

from agent_service.agents.base import AgentGraph, BaseAgent, Checkpointer
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.agents.errors import STEP_LIMIT_ERROR_DETAIL
from agent_service.core.settings import Settings
from agent_service.schema.stream import STREAM_EVENT_ADAPTER, ErrorEvent
from agent_service.service.app import create_app

RECURSION_LIMIT = 6


class StepState(MessagesState):
    remaining_steps: RemainingSteps


class StepCountingAgent(BaseAgent):
    """Mengulang satu node sampai sisa langkah habis, lalu menjawab jumlah langkahnya."""

    def build(
        self, model: BaseChatModel, checkpointer: Checkpointer, store: BaseStore | None = None
    ) -> AgentGraph:
        async def step(state: StepState) -> dict[str, list[AIMessage]]:
            return {"messages": [AIMessage(content=f"remaining={state['remaining_steps']}")]}

        def route(state: StepState) -> str:
            return END if state["remaining_steps"] <= 1 else "step"

        # pyrefly tidak mengenali TypedDict sebagai TypedDictLike milik LangGraph.
        builder = StateGraph(StepState)  # pyrefly: ignore[bad-specialization]
        builder.add_node("step", step)
        builder.add_edge(START, "step")
        builder.add_conditional_edges("step", route)
        return builder.compile(checkpointer=checkpointer)


class EndlessAgent(BaseAgent):
    """Graph tanpa kondisi berhenti, jadi selalu melewati `recursion_limit`."""

    def build(
        self, model: BaseChatModel, checkpointer: Checkpointer, store: BaseStore | None = None
    ) -> AgentGraph:
        async def loop(state: MessagesState) -> MessagesState:
            return {"messages": [AIMessage(content="again")]}

        # pyrefly tidak mengenali TypedDict sebagai TypedDictLike milik LangGraph.
        builder = StateGraph(MessagesState)  # pyrefly: ignore[bad-specialization]
        builder.add_node("loop", loop)
        builder.add_edge(START, "loop")
        builder.add_edge("loop", "loop")
        return builder.compile(checkpointer=checkpointer)


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        use_fake_model=True,
        database_url=database_url,
        agent_recursion_limit=RECURSION_LIMIT,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    agents = [
        ChatbotAgent(),
        StepCountingAgent(agent_id="steps", description="Counts steps"),
        EndlessAgent(agent_id="endless", description="Never stops"),
    ]
    return create_app(settings, agents=agents)


async def test_run_uses_the_configured_recursion_limit(client: AsyncClient) -> None:
    response = await client.post("/steps/invoke", json={"message": "go"})

    assert response.status_code == 200, response.text
    assert response.json()["content"] == "remaining=1"


async def test_invoke_past_the_recursion_limit_is_a_clear_error(client: AsyncClient) -> None:
    """Acceptance F47: run yang melewati `recursion_limit` berhenti dengan pesan error."""
    response = await client.post("/endless/invoke", json={"message": "go"})

    assert response.status_code == 500
    assert response.json() == {"detail": STEP_LIMIT_ERROR_DETAIL}


async def test_stream_past_the_recursion_limit_ends_with_an_error_frame(
    client: AsyncClient,
) -> None:
    async with client.stream("POST", "/endless/stream", json={"message": "go"}) as response:
        lines = [line async for line in response.aiter_lines() if line]

    assert lines[-1] == "data: [DONE]"
    last_event = STREAM_EVENT_ADAPTER.validate_json(lines[-2].removeprefix("data: "))
    assert last_event == ErrorEvent(content=STEP_LIMIT_ERROR_DETAIL)
