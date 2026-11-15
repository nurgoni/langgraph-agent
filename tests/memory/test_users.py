from collections.abc import AsyncIterator

import psycopg
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_service.memory.database import DatabaseEngineProvider
from agent_service.memory.users import USER_ROLES, UsernameTakenError, UserRepository

HASH = "$argon2id$fake-hash"


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    async with DatabaseEngineProvider(database_url) as database_engine:
        yield database_engine


@pytest.fixture
def users(engine: AsyncEngine) -> UserRepository:
    return UserRepository(engine)


def test_roles_match_database_constraint() -> None:
    assert USER_ROLES == ("user", "service")


async def test_created_user_can_be_found(users: UserRepository) -> None:
    created = await users.create("demo", HASH)

    found = await users.get_by_username("demo")

    assert found == created
    assert created.role == "user"
    assert len(created.user_id) == 36


async def test_service_role_is_stored(users: UserRepository) -> None:
    await users.create("worker", HASH, role="service")

    found = await users.get_by_username("worker")

    assert found is not None
    assert found.role == "service"


async def test_unknown_username_is_none(users: UserRepository) -> None:
    assert await users.get_by_username("nobody") is None


async def test_duplicate_username_is_rejected(users: UserRepository) -> None:
    await users.create("demo", HASH)

    with pytest.raises(UsernameTakenError, match="demo"):
        await users.create("demo", "$argon2id$other")


async def test_each_user_gets_its_own_id(users: UserRepository) -> None:
    first = await users.create("first", HASH)
    second = await users.create("second", HASH)

    assert first.user_id != second.user_id


async def test_database_rejects_unknown_role(database_url: str) -> None:
    with (
        psycopg.connect(database_url, autocommit=True) as connection,
        pytest.raises(psycopg.errors.CheckViolation),
    ):
        connection.execute(
            "INSERT INTO users (user_id, username, password_hash, role) "
            "VALUES (gen_random_uuid(), 'root', 'x', 'admin')"
        )
