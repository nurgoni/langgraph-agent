import pytest
from httpx import AsyncClient

from agent_service.llm.fake import DEFAULT_FAKE_RESPONSE
from agent_service.schema.responses import ChatHistory

OWNER = "user-a"


async def start_thread(client: AsyncClient, agent_path: str, message: str) -> None:
    body = {"message": message, "thread_id": "t1", "user_id": OWNER}
    response = await client.post(f"{agent_path}/invoke", json=body)
    assert response.status_code == 200, response.text


async def test_history_returns_messages_in_order(client: AsyncClient) -> None:
    await start_thread(client, "/chatbot", "pertama")
    await start_thread(client, "/chatbot", "kedua")

    response = await client.post("/chatbot/history", json={"thread_id": "t1", "user_id": OWNER})

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

    response = await client.post("/history", json={"thread_id": "t1", "user_id": OWNER})

    assert response.status_code == 200
    assert len(response.json()["messages"]) == 2


async def test_interrupted_thread_shows_messages_so_far(client: AsyncClient) -> None:
    await start_thread(client, "/interrupt", "Hai")

    response = await client.post("/interrupt/history", json={"thread_id": "t1", "user_id": OWNER})

    assert [m["content"] for m in response.json()["messages"]] == ["Hai"]


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/chatbot/history", {"thread_id": "t1", "user_id": "user-b"}),
        ("/chatbot/history", {"thread_id": "missing", "user_id": OWNER}),
        ("/tone/history", {"thread_id": "t1", "user_id": OWNER}),
    ],
)
async def test_unreadable_thread_is_404(
    client: AsyncClient, path: str, body: dict[str, str]
) -> None:
    await start_thread(client, "/chatbot", "rahasia")

    response = await client.post(path, json=body)

    assert response.status_code == 404
    assert response.json() == {"detail": f"Thread {body['thread_id']!r} not found"}


async def test_user_id_is_required(client: AsyncClient) -> None:
    response = await client.post("/chatbot/history", json={"thread_id": "t1"})

    assert response.status_code == 422
