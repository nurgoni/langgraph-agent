"""Acceptance F30 lewat API: persetujuan lewat balasan teks, `/memories`, dan isolasi user."""

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.store.base import BaseStore

from agent_service.agents.base import AgentGraph, BaseAgent, Checkpointer
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.llm.fake import FakeModel
from agent_service.memory.user_memories import UserMemoryRepository
from agent_service.schema.memories import MemoryList
from agent_service.schema.responses import ChatMessage

type AuthHeaders = Callable[..., dict[str, str]]
OWNER = "user-a"
PREFERENCE = "User prefers answers in Indonesian"
SAVE_REPLY = AIMessage(
    content="",
    tool_calls=[{"name": "save_memory", "args": {"memory": PREFERENCE}, "id": "save1"}],
)


class RememberingAgent(ChatbotAgent):
    """Chatbot ber-memory dengan model yang selalu meminta menyimpan `PREFERENCE` dulu."""

    def __init__(self) -> None:
        super().__init__(agent_id="remember", description="Saves a memory", use_memory=True)

    def build(
        self, model: BaseChatModel, checkpointer: Checkpointer, store: BaseStore | None = None
    ) -> AgentGraph:
        scripted = FakeModel(responses=[SAVE_REPLY, "Done.", "Halo!"])
        return super().build(scripted, checkpointer, store)


@pytest.fixture
def agents() -> list[BaseAgent]:
    return [ChatbotAgent(), RememberingAgent()]


def repository(app: FastAPI) -> UserMemoryRepository:
    return app.state.memory_repository


async def test_memory_is_saved_after_text_approval_and_listed(client: AsyncClient) -> None:
    body = {"message": "Tolong ingat aku suka jawaban bahasa Indonesia"}
    asked = await client.post("/remember/invoke", json=body)
    thread_id = asked.headers["X-Thread-Id"]
    before = MemoryList.model_validate((await client.get("/memories")).json())

    approved = await client.post("/remember/invoke", json={"message": "ya", "thread_id": thread_id})
    after = MemoryList.model_validate((await client.get("/memories")).json())

    assert PREFERENCE in ChatMessage.model_validate(asked.json()).content
    assert before.memories == []
    assert ChatMessage.model_validate(approved.json()).content == "Done."
    assert [memory.text for memory in after.memories] == [PREFERENCE]


async def test_declined_memory_is_not_listed(client: AsyncClient) -> None:
    asked = await client.post("/remember/invoke", json={"message": "Ingat ini"})
    thread_id = asked.headers["X-Thread-Id"]

    await client.post("/remember/invoke", json={"message": "jangan", "thread_id": thread_id})

    assert (await client.get("/memories")).json() == {"memories": []}


async def test_user_deletes_own_memory(app: FastAPI, client: AsyncClient) -> None:
    record = await repository(app).save(OWNER, "Likes tea")

    deleted = await client.delete(f"/memories/{record.memory_id}")
    again = await client.delete(f"/memories/{record.memory_id}")

    assert deleted.status_code == 204
    assert again.status_code == 404
    assert (await client.get("/memories")).json() == {"memories": []}


async def test_other_users_memories_are_invisible(
    app: FastAPI, client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    record = await repository(app).save(OWNER, "Owner secret")
    bob = auth_headers("user-b")

    listing = await client.get("/memories", headers=bob)
    deleted = await client.delete(f"/memories/{record.memory_id}", headers=bob)

    assert listing.json() == {"memories": []}
    assert deleted.status_code == 404
    assert deleted.json() == {"detail": f"Memory {record.memory_id!r} not found"}
    assert len(await repository(app).list_memories(OWNER)) == 1


@pytest.mark.parametrize(("method", "path"), [("GET", "/memories"), ("DELETE", "/memories/x")])
async def test_memories_need_a_token(anonymous_client: AsyncClient, method: str, path: str) -> None:
    response = await anonymous_client.request(method, path)

    assert response.status_code == 401
