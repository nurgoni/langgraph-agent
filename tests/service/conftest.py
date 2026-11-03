"""Fixture service: app dengan FakeModel, SQLite di `tmp_path`, dan lifespan yang berjalan."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from agent_service.core.settings import Settings
from agent_service.service.app import create_app

BASE_URL = "http://testserver"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, use_fake_model=True, sqlite_db_path=tmp_path / "test.db")


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Client HTTP in-process. Lifespan dijalankan manual karena `ASGITransport` melewatinya."""
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url=BASE_URL) as http_client:
            yield http_client
