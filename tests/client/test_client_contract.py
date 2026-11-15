"""Client asli terhadap service asli (in-process lewat ASGI, FakeModel, database Postgres test)."""

from collections.abc import AsyncIterator

import httpx
import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from agent_service.agents.base import AgentGraph, Checkpointer
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.client import AgentClient, AgentClientError
from agent_service.core.settings import Settings
from agent_service.llm.fake import DEFAULT_FAKE_RESPONSE, FakeModel
from agent_service.memory.database import DatabaseEngineProvider
from agent_service.memory.users import UserRepository
from agent_service.schema.stream import MessageEvent, ReasoningEvent, TokenEvent
from agent_service.service.app import create_app
from agent_service.service.auth import hash_password

BASE_URL = "http://testserver"
PASSWORD = "correct-horse"


THINKING_REPLY = AIMessage(
    content="Merah dan biru", additional_kwargs={"reasoning_content": "Pilih dua warna"}
)


class ThinkingAgent(ChatbotAgent):
    """Chatbot dengan model reasoning tiruan, untuk kontrak frame `reasoning` (FR-29)."""

    def __init__(self) -> None:
        super().__init__(agent_id="thinking", description="Reasons before answering")

    def build(self, model: BaseChatModel, checkpointer: Checkpointer) -> AgentGraph:
        return super().build(FakeModel(responses=[THINKING_REPLY]), checkpointer)


@pytest.fixture
async def transport(database_url: str) -> AsyncIterator[httpx.ASGITransport]:
    """Service asli dengan dua akun login: `alice` dan `bob`."""
    async with DatabaseEngineProvider(database_url) as engine:
        users = UserRepository(engine)
        for username in ("alice", "bob"):
            await users.create(username, hash_password(PASSWORD))
    settings = Settings(_env_file=None, use_fake_model=True, database_url=database_url)
    app = create_app(settings, agents=[ChatbotAgent(), ThinkingAgent()])
    async with app.router.lifespan_context(app):
        yield httpx.ASGITransport(app=app)


@pytest.fixture
async def client(transport: httpx.ASGITransport) -> AsyncIterator[AgentClient]:
    async with AgentClient(base_url=BASE_URL, async_transport=transport) as agent_client:
        await agent_client.alogin("alice", PASSWORD)
        yield agent_client


@pytest.fixture
async def other_client(transport: httpx.ASGITransport) -> AsyncIterator[AgentClient]:
    async with AgentClient(base_url=BASE_URL, async_transport=transport) as agent_client:
        await agent_client.alogin("bob", PASSWORD)
        yield agent_client


async def test_full_conversation_through_client(client: AgentClient) -> None:
    info = await client.aget_info()
    first = await client.ainvoke("Rencana liburan")

    async with client.astream("Lanjut", thread_id=first.thread_id) as run:
        events = [event async for event in run]
        streamed_thread = run.thread_id

    history = await client.aget_history(first.thread_id)
    threads = await client.aget_threads()

    assert info.default_agent == "chatbot"
    assert first.message.content == DEFAULT_FAKE_RESPONSE
    assert streamed_thread == first.thread_id
    assert "".join(e.content for e in events if isinstance(e, TokenEvent)) == DEFAULT_FAKE_RESPONSE
    assert any(isinstance(e, MessageEvent) for e in events)
    assert [m.type for m in history.messages] == ["human", "ai", "human", "ai"]
    assert [(t.thread_id, t.title) for t in threads.threads] == [
        (first.thread_id, "Rencana liburan")
    ]


async def test_rename_and_delete_through_client(client: AgentClient) -> None:
    reply = await client.ainvoke("Halo")

    summary = await client.arename_thread(reply.thread_id, "Judul baru")
    await client.adelete_thread(reply.thread_id)

    assert summary.title == "Judul baru"
    with pytest.raises(AgentClientError) as error_info:
        await client.aget_history(reply.thread_id)
    assert error_info.value.status_code == 404


async def test_service_errors_reach_client_with_status(client: AgentClient) -> None:
    client.agent_id = "ghost"
    with pytest.raises(AgentClientError) as not_found:
        await client.ainvoke("Halo")

    client.agent_id = "chatbot"
    with pytest.raises(AgentClientError) as invalid_config:
        await client.ainvoke("Halo", agent_config={"temperature": 1})

    assert not_found.value.status_code == 404
    assert invalid_config.value.status_code == 422
    assert isinstance(invalid_config.value.detail, list)


async def test_missing_token_is_401(transport: httpx.ASGITransport) -> None:
    async with AgentClient(base_url=BASE_URL, async_transport=transport) as anonymous:
        with pytest.raises(AgentClientError) as error_info:
            await anonymous.aget_info()

    assert error_info.value.status_code == 401


async def test_wrong_password_is_401(transport: httpx.ASGITransport) -> None:
    async with AgentClient(base_url=BASE_URL, async_transport=transport) as anonymous:
        with pytest.raises(AgentClientError) as error_info:
            await anonymous.alogin("alice", "wrong-password")

    assert error_info.value.status_code == 401
    assert not anonymous.has_access_token


async def test_other_user_cannot_touch_thread(
    client: AgentClient, other_client: AgentClient
) -> None:
    reply = await client.ainvoke("Rahasia Alice")

    attempts = [
        other_client.aget_history(reply.thread_id),
        other_client.ainvoke("Lanjut", thread_id=reply.thread_id),
        other_client.arename_thread(reply.thread_id, "Dibajak"),
        other_client.adelete_thread(reply.thread_id),
    ]
    statuses = []
    for attempt in attempts:
        with pytest.raises(AgentClientError) as error_info:
            await attempt
        statuses.append(error_info.value.status_code)

    assert statuses == [404, 404, 404, 404]
    assert (await other_client.aget_threads()).threads == []
    assert len((await client.aget_history(reply.thread_id)).messages) == 2


async def test_reasoning_reaches_client_and_history(client: AgentClient) -> None:
    client.agent_id = "thinking"

    async with client.astream("Dua warna?") as run:
        events = [event async for event in run]
        thread_id = run.thread_id
    history = await client.aget_history(thread_id)

    reasoning = "".join(e.content for e in events if isinstance(e, ReasoningEvent))
    first_token = next(i for i, e in enumerate(events) if isinstance(e, TokenEvent))
    assert reasoning == "Pilih dua warna"
    assert all(isinstance(e, ReasoningEvent) for e in events[:first_token])
    assert history.messages[-1].reasoning == "Pilih dua warna"
