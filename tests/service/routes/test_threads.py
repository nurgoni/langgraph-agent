import pytest
from httpx import AsyncClient

from agent_service.schema.requests import TITLE_MAX_LENGTH
from agent_service.schema.responses import ThreadSummary, UserThreads

USER_A = "user-a"
USER_B = "user-b"


async def start_thread(
    client: AsyncClient, thread_id: str, user_id: str, message: str, agent: str = "chatbot"
) -> None:
    body = {"message": message, "thread_id": thread_id, "user_id": user_id}
    response = await client.post(f"/{agent}/invoke", json=body)
    assert response.status_code == 200, response.text


async def list_threads(client: AsyncClient, path: str, **params: str | int) -> UserThreads:
    response = await client.get(path, params=params)
    assert response.status_code == 200, response.text
    return UserThreads.model_validate(response.json())


async def test_user_sees_only_own_threads(client: AsyncClient) -> None:
    await start_thread(client, "a1", USER_A, "Rencana liburan")
    await start_thread(client, "b1", USER_B, "Rahasia B")

    threads = await list_threads(client, "/chatbot/threads", user_id=USER_A)

    assert [(t.thread_id, t.title) for t in threads.threads] == [("a1", "Rencana liburan")]


async def test_default_agent_route_lists_chatbot_threads(client: AsyncClient) -> None:
    await start_thread(client, "a1", USER_A, "Halo")
    await start_thread(client, "a2", USER_A, "Halo tone", agent="tone")

    threads = await list_threads(client, "/threads", user_id=USER_A)

    assert [t.thread_id for t in threads.threads] == ["a1"]


async def test_limit_is_applied(client: AsyncClient) -> None:
    for index in range(3):
        await start_thread(client, f"t{index}", USER_A, "Halo")

    threads = await list_threads(client, "/chatbot/threads", user_id=USER_A, limit=2)

    assert [t.thread_id for t in threads.threads] == ["t2", "t1"]


@pytest.mark.parametrize("limit", [0, 101])
async def test_limit_out_of_range_is_422(client: AsyncClient, limit: int) -> None:
    response = await client.get("/chatbot/threads", params={"user_id": USER_A, "limit": limit})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "limit"]


async def test_user_id_is_required(client: AsyncClient) -> None:
    response = await client.get("/chatbot/threads")

    assert response.status_code == 422


async def test_unknown_agent_is_404(client: AsyncClient) -> None:
    response = await client.get("/ghost/threads", params={"user_id": USER_A})

    assert response.status_code == 404


async def test_rename_returns_new_title(client: AsyncClient) -> None:
    await start_thread(client, "a1", USER_A, "Judul otomatis")

    response = await client.patch(
        "/chatbot/threads/a1", json={"user_id": USER_A, "title": "  Rencana liburan  "}
    )

    assert response.status_code == 200
    summary = ThreadSummary.model_validate(response.json())
    assert (summary.thread_id, summary.title) == ("a1", "Rencana liburan")


async def test_rename_on_default_agent_route(client: AsyncClient) -> None:
    await start_thread(client, "a1", USER_A, "Halo")

    response = await client.patch("/threads/a1", json={"user_id": USER_A, "title": "Baru"})

    assert response.status_code == 200
    assert response.json()["title"] == "Baru"


async def test_rename_of_other_users_thread_is_404(client: AsyncClient) -> None:
    await start_thread(client, "a1", USER_A, "punya A")

    response = await client.patch("/chatbot/threads/a1", json={"user_id": USER_B, "title": "X"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Thread 'a1' not found"}


@pytest.mark.parametrize("title", ["", "   ", "x" * (TITLE_MAX_LENGTH + 1)])
async def test_invalid_title_is_422(client: AsyncClient, title: str) -> None:
    await start_thread(client, "a1", USER_A, "Halo")

    response = await client.patch("/chatbot/threads/a1", json={"user_id": USER_A, "title": title})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "title"]


async def test_rename_on_unknown_agent_is_404(client: AsyncClient) -> None:
    response = await client.patch("/ghost/threads/a1", json={"user_id": USER_A, "title": "X"})

    assert response.status_code == 404


async def test_delete_removes_thread_everywhere(client: AsyncClient) -> None:
    await start_thread(client, "a1", USER_A, "hapus aku")

    response = await client.delete("/chatbot/threads/a1", params={"user_id": USER_A})

    assert response.status_code == 204
    assert response.content == b""
    history = await client.post("/chatbot/history", json={"thread_id": "a1", "user_id": USER_A})
    assert history.status_code == 404
    threads = await list_threads(client, "/chatbot/threads", user_id=USER_A)
    assert threads.threads == []


async def test_delete_on_default_agent_route(client: AsyncClient) -> None:
    await start_thread(client, "a1", USER_A, "Halo")

    response = await client.delete("/threads/a1", params={"user_id": USER_A})

    assert response.status_code == 204


async def test_delete_of_other_users_thread_is_404(client: AsyncClient) -> None:
    await start_thread(client, "a1", USER_A, "punya A")

    response = await client.delete("/chatbot/threads/a1", params={"user_id": USER_B})
    history = await client.post("/chatbot/history", json={"thread_id": "a1", "user_id": USER_A})

    assert response.status_code == 404
    assert history.status_code == 200


async def test_deleted_thread_id_can_start_fresh(client: AsyncClient) -> None:
    await start_thread(client, "a1", USER_A, "lama")
    await client.delete("/chatbot/threads/a1", params={"user_id": USER_A})

    await start_thread(client, "a1", USER_A, "baru")
    history = await client.post("/chatbot/history", json={"thread_id": "a1", "user_id": USER_A})

    assert [m["content"] for m in history.json()["messages"]][0] == "baru"


async def test_delete_requires_user_id(client: AsyncClient) -> None:
    response = await client.delete("/chatbot/threads/a1")

    assert response.status_code == 422
