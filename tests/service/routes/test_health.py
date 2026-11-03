from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agent_service.core.settings import Settings
from agent_service.service.app import create_app


@pytest.fixture
async def secured_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        _env_file=None,
        use_fake_model=True,
        sqlite_db_path=tmp_path / "test.db",
        auth_secret="s3cret",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_needs_no_token_when_auth_is_enabled(secured_client: AsyncClient) -> None:
    response = await secured_client.get("/health")

    assert response.status_code == 200


async def test_info_needs_token_when_auth_is_enabled(secured_client: AsyncClient) -> None:
    unauthorized = await secured_client.get("/info")
    authorized = await secured_client.get("/info", headers={"Authorization": "Bearer s3cret"})

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
