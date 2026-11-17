"""Fixture service: app dengan FakeModel, database Postgres test, lifespan, agent fake, dan token.

`client` membawa access token milik `OWNER`. Token user lain dibuat dengan fixture `auth_headers`,
dan request tanpa token memakai `anonymous_client`.
"""

from collections.abc import AsyncIterator, Callable

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.store.base import BaseStore
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict

from agent_service.agents.base import AgentGraph, BaseAgent, Checkpointer
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.core.settings import Settings
from agent_service.memory.users import UserRecord, UserRole
from agent_service.service.app import create_app

BASE_URL = "http://testserver"
OWNER = "user-a"

type AuthHeaders = Callable[..., dict[str, str]]
INTERRUPT_QUESTION = "What is your name?"


class InterruptAgent(BaseAgent):
    """Bertanya lewat `interrupt()`, lalu menyapa dengan jawaban dari resume."""

    def build(
        self, model: BaseChatModel, checkpointer: Checkpointer, store: BaseStore | None = None
    ) -> AgentGraph:
        async def ask(state: MessagesState) -> MessagesState:
            name = interrupt(INTERRUPT_QUESTION)
            return {"messages": [AIMessage(content=f"Hello {name}")]}

        # pyrefly tidak mengenali TypedDict sebagai TypedDictLike milik LangGraph.
        builder = StateGraph(MessagesState)  # pyrefly: ignore[bad-specialization]
        builder.add_node("ask", ask)
        builder.add_edge(START, "ask")
        builder.add_edge("ask", END)
        return builder.compile(checkpointer=checkpointer)


class ToneConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tone: str = "neutral"
    max_words: int = 10


class ToneEchoAgent(BaseAgent):
    """Membalas dengan nilai `tone` dari `configurable`, untuk membuktikan config sampai ke node."""

    config_schema = ToneConfig

    def build(
        self, model: BaseChatModel, checkpointer: Checkpointer, store: BaseStore | None = None
    ) -> AgentGraph:
        async def echo(state: MessagesState, config: RunnableConfig) -> MessagesState:
            tone = config["configurable"]["tone"]
            return {"messages": [AIMessage(content=f"tone={tone}")]}

        # pyrefly tidak mengenali TypedDict sebagai TypedDictLike milik LangGraph.
        builder = StateGraph(MessagesState)  # pyrefly: ignore[bad-specialization]
        builder.add_node("echo", echo)
        builder.add_edge(START, "echo")
        builder.add_edge("echo", END)
        return builder.compile(checkpointer=checkpointer)


@pytest.fixture
def interrupt_agent() -> BaseAgent:
    return InterruptAgent(agent_id="interrupt", description="Asks for a name")


@pytest.fixture
def tone_agent() -> BaseAgent:
    return ToneEchoAgent(agent_id="tone", description="Echoes the tone config")


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(_env_file=None, use_fake_model=True, database_url=database_url)


@pytest.fixture
def agents(interrupt_agent: BaseAgent, tone_agent: BaseAgent) -> list[BaseAgent]:
    return [ChatbotAgent(), interrupt_agent, tone_agent]


@pytest.fixture
def app(settings: Settings, agents: list[BaseAgent]) -> FastAPI:
    return create_app(settings, agents=agents)


def bearer_headers(app: FastAPI, user_id: str, role: UserRole = "user") -> dict[str, str]:
    """Header `Authorization` dengan token asli dari authenticator app, tanpa akun di database."""
    user = UserRecord(user_id=user_id, username=user_id, password_hash="", role=role)
    token = app.state.authenticator.issue_token(user)
    return {"Authorization": f"Bearer {token.access_token}"}


@pytest.fixture
async def anonymous_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Client HTTP in-process tanpa token. Lifespan dijalankan manual karena `ASGITransport`
    melewatinya."""
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url=BASE_URL) as http_client:
            yield http_client


@pytest.fixture
def client(app: FastAPI, anonymous_client: AsyncClient) -> AsyncClient:
    """Client yang sama dengan `anonymous_client`, ditambah access token milik `OWNER`."""
    anonymous_client.headers.update(bearer_headers(app, OWNER))
    return anonymous_client


@pytest.fixture
def auth_headers(app: FastAPI, anonymous_client: AsyncClient) -> AuthHeaders:
    """Pembuat header token untuk user lain, misalnya `auth_headers("user-b")`."""

    def headers_for(user_id: str, role: UserRole = "user") -> dict[str, str]:
        return bearer_headers(app, user_id, role)

    return headers_for
