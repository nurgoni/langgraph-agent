"""Service in-process (FakeModel, Postgres test) dengan `AgentClient` asli untuk test eval."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport

from agent_service.client import AgentClient
from agent_service.core.settings import Settings
from agent_service.memory.users import UserRecord
from agent_service.service.app import create_app

BASE_URL = "http://testserver"


@pytest.fixture
async def eval_client(database_url: str) -> AsyncIterator[AgentClient]:
    """Client service account terhadap app dengan agent dan project bawaan."""
    settings = Settings(_env_file=None, use_fake_model=True, database_url=database_url)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        account = UserRecord(user_id="evals", username="evals", password_hash="", role="service")
        token = app.state.authenticator.issue_token(account).access_token
        transport = ASGITransport(app=app)
        async with AgentClient(BASE_URL, access_token=token, async_transport=transport) as client:
            yield client
