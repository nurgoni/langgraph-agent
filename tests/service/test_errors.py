import logging

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import BaseModel, Field

from agent_service.agents.errors import AgentNotFoundError, AgentUnavailableError
from agent_service.llm.factory import ModelNotConfiguredError, UnknownModelError
from agent_service.service.errors import INTERNAL_ERROR_DETAIL
from agent_service.service.thread_access import ThreadNotFoundError

DOMAIN_ERRORS: dict[str, Exception] = {
    "not-found": AgentNotFoundError("ghost"),
    "thread-not-found": ThreadNotFoundError("t9"),
    "unavailable": AgentUnavailableError("broken"),
    "unknown-model": UnknownModelError("gpt-x", ["fake"]),
    "not-configured": ModelNotConfiguredError("no base url"),
}


class EchoBody(BaseModel):
    message: str = Field(min_length=1)


@pytest.fixture
def app(app: FastAPI) -> FastAPI:
    """App standar ditambah route dummy yang melempar error tertentu."""

    @app.get("/raise/{name}")
    async def raise_error(name: str) -> None:
        raise DOMAIN_ERRORS[name]

    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("secret internal state")

    @app.post("/echo")
    async def echo(body: EchoBody) -> EchoBody:
        return body

    return app


@pytest.mark.parametrize(
    ("name", "expected_status", "expected_detail"),
    [
        ("not-found", 404, "Agent 'ghost' not found"),
        ("thread-not-found", 404, "Thread 't9' not found"),
        ("unavailable", 503, "Agent 'broken' is unavailable"),
        ("unknown-model", 422, "Unknown model 'gpt-x'. Available models: ['fake']"),
        ("not-configured", 503, "no base url"),
    ],
)
async def test_domain_error_maps_to_status_and_detail(
    client: AsyncClient, name: str, expected_status: int, expected_detail: str
) -> None:
    response = await client.get(f"/raise/{name}")

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}


async def test_unexpected_error_hides_details(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        response = await client.get("/crash")

    assert response.status_code == 500
    assert response.json() == {"detail": INTERNAL_ERROR_DETAIL}
    assert "secret internal state" not in response.text
    assert "Unhandled error on GET /crash" in caplog.text


async def test_request_validation_keeps_field_details(client: AsyncClient) -> None:
    response = await client.post("/echo", json={"message": ""})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["loc"] == ["body", "message"]
