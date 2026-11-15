from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_service.core.settings import Settings
from agent_service.memory.database import DatabaseEngineProvider
from agent_service.memory.users import UserRecord, UserRepository
from agent_service.service.app import create_app
from agent_service.service.auth import (
    INVALID_CREDENTIALS_DETAIL,
    INVALID_TOKEN_DETAIL,
    JWT_ALGORITHM,
    Authenticator,
    InvalidCredentialsError,
    InvalidTokenError,
    hash_password,
)

USERNAME = "demo"
PASSWORD = "correct-horse"
TTL_SECONDS = 600
OTHER_SECRET = "another-secret-that-is-also-32-chars"
ALLOWED_ORIGIN = "http://localhost:5173"
OTHER_ORIGIN = "https://evil.example"


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    async with DatabaseEngineProvider(database_url) as database_engine:
        yield database_engine


@pytest.fixture
async def demo_user(engine: AsyncEngine) -> UserRecord:
    return await UserRepository(engine).create(USERNAME, hash_password(PASSWORD))


@pytest.fixture
def authenticator(engine: AsyncEngine, test_jwt_secret: str) -> Authenticator:
    return Authenticator(UserRepository(engine), test_jwt_secret, TTL_SECONDS)


# ---------------- Authenticator


async def test_login_issues_token_for_the_user(
    authenticator: Authenticator, demo_user: UserRecord
) -> None:
    token = await authenticator.login(USERNAME, PASSWORD)

    principal = authenticator.verify_token(token.access_token)
    assert (token.user_id, token.username, token.role) == (demo_user.user_id, USERNAME, "user")
    assert token.expires_in == TTL_SECONDS
    assert (principal.user_id, principal.role) == (demo_user.user_id, "user")


@pytest.mark.parametrize(("username", "password"), [(USERNAME, "wrong"), ("nobody", PASSWORD)])
async def test_wrong_password_and_unknown_user_fail_the_same_way(
    authenticator: Authenticator, demo_user: UserRecord, username: str, password: str
) -> None:
    with pytest.raises(InvalidCredentialsError) as error_info:
        await authenticator.login(username, password)

    assert str(error_info.value) == INVALID_CREDENTIALS_DETAIL


async def test_service_role_is_carried_in_token(
    authenticator: Authenticator, engine: AsyncEngine
) -> None:
    await UserRepository(engine).create("worker", hash_password(PASSWORD), role="service")

    token = await authenticator.login("worker", PASSWORD)

    assert authenticator.verify_token(token.access_token).role == "service"


async def test_expired_token_is_rejected(engine: AsyncEngine, test_jwt_secret: str) -> None:
    def long_ago() -> datetime:
        return datetime.now(UTC) - timedelta(seconds=TTL_SECONDS * 2)

    past = Authenticator(UserRepository(engine), test_jwt_secret, TTL_SECONDS, clock=long_ago)
    user = UserRecord(user_id="u1", username="u1", password_hash="", role="user")
    token = past.issue_token(user).access_token

    with pytest.raises(InvalidTokenError):
        past.verify_token(token)


async def test_token_signed_with_another_secret_is_rejected(
    engine: AsyncEngine, authenticator: Authenticator
) -> None:
    forger = Authenticator(UserRepository(engine), OTHER_SECRET, TTL_SECONDS)
    user = UserRecord(user_id="u1", username="u1", password_hash="", role="user")

    with pytest.raises(InvalidTokenError):
        authenticator.verify_token(forger.issue_token(user).access_token)


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "u1", "role": "admin"},
        {"sub": "u1"},
        {"role": "user"},
    ],
)
async def test_token_with_bad_claims_is_rejected(
    authenticator: Authenticator, test_jwt_secret: str, claims: dict[str, str]
) -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {**claims, "iat": now, "exp": now + timedelta(minutes=1)},
        test_jwt_secret,
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(InvalidTokenError):
        authenticator.verify_token(token)


async def test_unsigned_token_is_rejected(authenticator: Authenticator) -> None:
    token = jwt.encode({"sub": "u1", "role": "user"}, key=None, algorithm="none")

    with pytest.raises(InvalidTokenError):
        authenticator.verify_token(token)


def test_password_hash_is_argon2_and_salted() -> None:
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)

    assert first.startswith("$argon2id$")
    assert first != second


# ---------------- HTTP


async def test_login_endpoint_returns_usable_token(
    anonymous_client: AsyncClient, demo_user: UserRecord
) -> None:
    response = await anonymous_client.post(
        "/auth/login", json={"username": " Demo ", "password": PASSWORD}
    )
    token = response.json()["access_token"]

    info = await anonymous_client.get("/info", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert info.status_code == 200


async def test_failed_login_is_401_with_challenge(
    anonymous_client: AsyncClient, demo_user: UserRecord
) -> None:
    response = await anonymous_client.post(
        "/auth/login", json={"username": USERNAME, "password": "wrong"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": INVALID_CREDENTIALS_DETAIL}
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/info"),
        ("POST", "/chatbot/invoke"),
        ("POST", "/chatbot/stream"),
        ("POST", "/chatbot/history"),
        ("GET", "/chatbot/threads"),
        ("PATCH", "/chatbot/threads/t1"),
        ("DELETE", "/chatbot/threads/t1"),
    ],
)
@pytest.mark.parametrize("authorization", [None, "Bearer not-a-jwt", "Basic dXNlcjpwYXNz"])
async def test_protected_endpoints_need_a_valid_token(
    anonymous_client: AsyncClient, method: str, path: str, authorization: str | None
) -> None:
    headers = {} if authorization is None else {"Authorization": authorization}

    response = await anonymous_client.request(method, path, headers=headers, json={})

    assert response.status_code == 401
    assert response.json() == {"detail": INVALID_TOKEN_DETAIL}
    assert response.headers["www-authenticate"] == "Bearer"


async def test_health_and_login_need_no_token(anonymous_client: AsyncClient) -> None:
    health = await anonymous_client.get("/health")
    login = await anonymous_client.post("/auth/login", json={"username": "nobody", "password": "y"})

    assert health.status_code == 200
    assert login.json() == {"detail": INVALID_CREDENTIALS_DETAIL}


# ---------------- CORS


@pytest.fixture
async def cors_client(database_url: str) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        _env_file=None,
        use_fake_model=True,
        database_url=database_url,
        cors_origins=[ALLOWED_ORIGIN],
    )
    app: FastAPI = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


def preflight_headers(origin: str) -> dict[str, str]:
    return {
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization, content-type",
    }


async def test_preflight_from_allowed_origin_succeeds(cors_client: AsyncClient) -> None:
    response = await cors_client.options(
        "/chatbot/stream", headers=preflight_headers(ALLOWED_ORIGIN)
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


async def test_preflight_from_other_origin_is_rejected(cors_client: AsyncClient) -> None:
    response = await cors_client.options("/chatbot/stream", headers=preflight_headers(OTHER_ORIGIN))

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


async def test_thread_id_header_is_exposed_to_browsers(cors_client: AsyncClient) -> None:
    response = await cors_client.get("/health", headers={"Origin": ALLOWED_ORIGIN})

    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert response.headers["access-control-expose-headers"] == "X-Thread-Id"


async def test_no_cors_origins_means_no_cross_origin_access(anonymous_client: AsyncClient) -> None:
    response = await anonymous_client.options(
        "/chatbot/stream", headers=preflight_headers(ALLOWED_ORIGIN)
    )

    assert response.status_code == 400
