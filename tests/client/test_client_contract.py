"""Client asli terhadap service asli (in-process lewat ASGI, FakeModel, SQLite sementara)."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from agent_service.client import AgentClient, AgentClientError
from agent_service.core.settings import Settings
from agent_service.llm.fake import DEFAULT_FAKE_RESPONSE
from agent_service.schema.stream import MessageEvent, TokenEvent
from agent_service.service.app import create_app

SECRET = "s3cret"
OWNER = "user-a"


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[AgentClient]:
    settings = Settings(
        _env_file=None,
        use_fake_model=True,
        sqlite_db_path=tmp_path / "contract.db",
        auth_secret=SECRET,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with AgentClient(
            base_url="http://testserver", auth_secret=SECRET, async_transport=transport
        ) as agent_client:
            yield agent_client


async def test_full_conversation_through_client(client: AgentClient) -> None:
    info = await client.aget_info()
    first = await client.ainvoke("Rencana liburan", user_id=OWNER)

    async with client.astream("Lanjut", thread_id=first.thread_id, user_id=OWNER) as run:
        events = [event async for event in run]
        streamed_thread = run.thread_id

    history = await client.aget_history(first.thread_id, OWNER)
    threads = await client.aget_threads(OWNER)

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
    reply = await client.ainvoke("Halo", user_id=OWNER)

    summary = await client.arename_thread(reply.thread_id, OWNER, "Judul baru")
    await client.adelete_thread(reply.thread_id, OWNER)

    assert summary.title == "Judul baru"
    with pytest.raises(AgentClientError) as error_info:
        await client.aget_history(reply.thread_id, OWNER)
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


async def test_missing_token_is_401(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None, use_fake_model=True, sqlite_db_path=tmp_path / "x.db", auth_secret=SECRET
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with AgentClient(base_url="http://testserver", async_transport=transport) as client:
            with pytest.raises(AgentClientError) as error_info:
                await client.aget_info()

    assert error_info.value.status_code == 401
