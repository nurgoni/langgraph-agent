from collections.abc import Callable
from typing import Any

from httpx import AsyncClient

from agent_service.llm.fake import DEFAULT_FAKE_RESPONSE
from agent_service.schema.headers import THREAD_ID_HEADER
from agent_service.schema.responses import ChatMessage

INTRUDER = "user-b"

type AuthHeaders = Callable[..., dict[str, str]]


async def invoke(client: AsyncClient, path: str, **body: Any) -> ChatMessage:  # Any: body JSON
    response = await client.post(path, json=body)
    assert response.status_code == 200, response.text
    return ChatMessage.model_validate(response.json())


async def test_invoke_returns_final_ai_message(client: AsyncClient) -> None:
    message = await invoke(client, "/chatbot/invoke", message="Halo")

    assert message.type == "ai"
    assert message.content == DEFAULT_FAKE_RESPONSE
    assert message.run_id


async def test_default_agent_route_uses_chatbot(client: AsyncClient) -> None:
    message = await invoke(client, "/invoke", message="Halo")

    assert message.content == DEFAULT_FAKE_RESPONSE


async def test_generated_thread_id_is_returned_without_user_header(client: AsyncClient) -> None:
    response = await client.post("/chatbot/invoke", json={"message": "Halo"})

    assert response.headers[THREAD_ID_HEADER]
    assert "x-user-id" not in response.headers


async def test_given_thread_id_is_echoed_in_header(client: AsyncClient) -> None:
    response = await client.post("/chatbot/invoke", json={"message": "Halo", "thread_id": "t1"})

    assert response.headers[THREAD_ID_HEADER] == "t1"


async def test_user_id_in_body_cannot_impersonate_owner(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    await invoke(client, "/chatbot/invoke", message="rahasia", thread_id="t1")

    response = await client.post(
        "/chatbot/invoke",
        json={"message": "baca", "thread_id": "t1", "user_id": "user-a"},
        headers=auth_headers(INTRUDER),
    )

    assert response.status_code == 404


async def test_interrupt_is_returned_then_resumed(client: AsyncClient) -> None:
    question = await invoke(client, "/interrupt/invoke", message="Hai", thread_id="t1")
    answer = await invoke(client, "/interrupt/invoke", message="Budi", thread_id="t1")

    assert question.content == "What is your name?"
    assert answer.content == "Hello Budi"


async def test_valid_agent_config_reaches_graph_node(client: AsyncClient) -> None:
    message = await invoke(client, "/tone/invoke", message="Hai", agent_config={"tone": "formal"})

    assert message.content == "tone=formal"


async def test_invalid_agent_config_is_422_with_field(client: AsyncClient) -> None:
    body = {"message": "Hai", "agent_config": {"tone": "formal", "max_words": "many"}}

    response = await client.post("/tone/invoke", json=body)

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", "agent_config", "max_words"]


async def test_reserved_agent_config_key_is_422(client: AsyncClient) -> None:
    body = {"message": "Hai", "agent_config": {"user_id": "x"}}

    response = await client.post("/chatbot/invoke", json=body)

    assert response.status_code == 422


async def test_unknown_model_is_422(client: AsyncClient) -> None:
    response = await client.post("/chatbot/invoke", json={"message": "Hai", "model": "gpt-x"})

    assert response.status_code == 422
    assert "gpt-x" in response.json()["detail"]


async def test_unknown_agent_is_404(client: AsyncClient) -> None:
    response = await client.post("/ghost/invoke", json={"message": "Hai"})

    assert response.status_code == 404


async def test_other_users_thread_cannot_be_continued(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    await invoke(client, "/chatbot/invoke", message="rahasia", thread_id="t1")

    response = await client.post(
        "/chatbot/invoke",
        json={"message": "baca", "thread_id": "t1"},
        headers=auth_headers(INTRUDER),
    )

    assert response.status_code == 404


async def test_thread_cannot_be_continued_by_another_agent(client: AsyncClient) -> None:
    await invoke(client, "/chatbot/invoke", message="Hai", thread_id="t1")

    response = await client.post("/tone/invoke", json={"message": "Hai", "thread_id": "t1"})

    assert response.status_code == 404
