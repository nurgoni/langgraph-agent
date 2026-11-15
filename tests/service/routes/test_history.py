from collections.abc import Callable

import pytest
from httpx import AsyncClient

from agent_service.llm.fake import DEFAULT_FAKE_RESPONSE
from agent_service.schema.responses import ChatHistory

INTRUDER = "user-b"

type AuthHeaders = Callable[..., dict[str, str]]


async def start_thread(client: AsyncClient, agent_path: str, message: str) -> None:
    body = {"message": message, "thread_id": "t1"}
    response = await client.post(f"{agent_path}/invoke", json=body)
    assert response.status_code == 200, response.text


async def test_history_returns_messages_in_order(client: AsyncClient) -> None:
    await start_thread(client, "/chatbot", "pertama")
    await start_thread(client, "/chatbot", "kedua")

    response = await client.post("/chatbot/history", json={"thread_id": "t1"})

    assert response.status_code == 200
    history = ChatHistory.model_validate(response.json())
    assert [(m.type, m.content) for m in history.messages] == [
        ("human", "pertama"),
        ("ai", DEFAULT_FAKE_RESPONSE),
        ("human", "kedua"),
        ("ai", DEFAULT_FAKE_RESPONSE),
    ]


async def test_default_agent_route_reads_chatbot_thread(client: AsyncClient) -> None:
    await start_thread(client, "/chatbot", "Hai")

    response = await client.post("/history", json={"thread_id": "t1"})

    assert response.status_code == 200
    assert len(response.json()["messages"]) == 2


async def test_interrupted_thread_shows_messages_so_far(client: AsyncClient) -> None:
    await start_thread(client, "/interrupt", "Hai")

    response = await client.post("/interrupt/history", json={"thread_id": "t1"})

    assert [m["content"] for m in response.json()["messages"]] == ["Hai"]


@pytest.mark.parametrize(
    ("path", "thread_id", "reader"),
    [
        ("/chatbot/history", "t1", INTRUDER),
        ("/chatbot/history", "missing", None),
        ("/tone/history", "t1", None),
    ],
)
async def test_unreadable_thread_is_404(
    client: AsyncClient,
    auth_headers: AuthHeaders,
    path: str,
    thread_id: str,
    reader: str | None,
) -> None:
    await start_thread(client, "/chatbot", "rahasia")
    headers = None if reader is None else auth_headers(reader)

    response = await client.post(path, json={"thread_id": thread_id}, headers=headers)

    assert response.status_code == 404
    assert response.json() == {"detail": f"Thread {thread_id!r} not found"}


async def test_thread_id_is_required(client: AsyncClient) -> None:
    response = await client.post("/chatbot/history", json={})

    assert response.status_code == 422
