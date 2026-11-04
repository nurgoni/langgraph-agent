from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import APIRouter, Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from agent_service.core.settings import Settings
from agent_service.service.app import create_app
from agent_service.service.auth import UNAUTHORIZED_DETAIL, verify_bearer

SECRET = "s3cret"
PROTECTED_PATH = "/protected"


def add_protected_route(app: FastAPI) -> None:
    router = APIRouter(dependencies=[Depends(verify_bearer)])

    @router.get(PROTECTED_PATH)
    async def protected() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(router)


async def open_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


@pytest.fixture
async def secured_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        _env_file=None,
        use_fake_model=True,
        sqlite_db_path=tmp_path / "test.db",
        auth_secret=SECRET,
    )
    app = create_app(settings)
    add_protected_route(app)
    async for client in open_client(app):
        yield client


@pytest.fixture
async def open_access_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    add_protected_route(app)
    async for client in open_client(app):
        yield client


async def test_valid_token_is_accepted(secured_client: AsyncClient) -> None:
    response = await secured_client.get(
        PROTECTED_PATH, headers={"Authorization": f"Bearer {SECRET}"}
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong"}, {"Authorization": f"Basic {SECRET}"}],
)
async def test_missing_or_wrong_token_is_rejected(
    secured_client: AsyncClient, headers: dict[str, str]
) -> None:
    response = await secured_client.get(PROTECTED_PATH, headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": UNAUTHORIZED_DETAIL}
    assert response.headers["www-authenticate"] == "Bearer"


async def test_without_auth_secret_every_request_passes(open_access_client: AsyncClient) -> None:
    response = await open_access_client.get(PROTECTED_PATH)

    assert response.status_code == 200
