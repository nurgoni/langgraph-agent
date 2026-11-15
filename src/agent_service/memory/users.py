"""Akun login di tabel `users` (FR-33).

Repository ini hanya menyimpan dan membaca akun. Hash password dibuat dan diverifikasi oleh
layer service (`service/auth.py`), jadi `memory/` tidak bergantung pada library kriptografi.
"""

from dataclasses import dataclass
from typing import Final, Literal, get_args
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_service.memory.tables import users_table

# `service` dipakai klien mesin seperti worker (F41) dan eval (F31).
type UserRole = Literal["user", "service"]
USER_ROLES: Final[tuple[str, ...]] = get_args(UserRole.__value__)
DEFAULT_ROLE: Final[UserRole] = "user"


class UsernameTakenError(ValueError):
    """Username sudah dipakai akun lain.

    >>> str(UsernameTakenError("demo"))
    "Username 'demo' is already taken"
    """

    def __init__(self, username: str) -> None:
        """Inisialisasi error.

        Args:
            username: Username yang bentrok.
        """
        super().__init__(f"Username {username!r} is already taken")
        self.username = username


@dataclass(frozen=True)
class UserRecord:
    """Satu baris tabel `users`."""

    user_id: str
    username: str
    password_hash: str
    role: UserRole


class UserRepository:
    """Membuat dan mencari akun login.

    Engine dimiliki `DatabaseEngineProvider` di lifespan atau di perintah `manage`.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        """Inisialisasi repository.

        Args:
            engine: Engine ke database yang sudah dimigrasi.
        """
        self._engine = engine

    async def create(
        self, username: str, password_hash: str, role: UserRole = DEFAULT_ROLE
    ) -> UserRecord:
        """Simpan akun baru dengan `user_id` UUID baru.

        Args:
            username: Username yang sudah divalidasi dan dinormalisasi (huruf kecil).
            password_hash: Hash password, bukan password asli.
            role: `user` untuk manusia, `service` untuk klien mesin.

        Returns:
            Akun yang tersimpan.

        Raises:
            UsernameTakenError: Jika username sudah dipakai.
        """
        user = UserRecord(
            user_id=str(uuid4()), username=username, password_hash=password_hash, role=role
        )
        statement = users_table.insert().values(
            user_id=user.user_id,
            username=user.username,
            password_hash=user.password_hash,
            role=user.role,
        )
        try:
            async with self._engine.begin() as connection:
                await connection.execute(statement)
        except IntegrityError as error:
            raise UsernameTakenError(username) from error
        return user

    async def get_by_username(self, username: str) -> UserRecord | None:
        """Cari akun berdasarkan username.

        Args:
            username: Username yang sudah dinormalisasi (huruf kecil).

        Returns:
            Akun, atau `None` jika tidak ada.
        """
        query = select(
            users_table.c.user_id,
            users_table.c.username,
            users_table.c.password_hash,
            users_table.c.role,
        ).where(users_table.c.username == username)
        async with self._engine.connect() as connection:
            row = (await connection.execute(query)).first()
        if row is None:
            return None
        return UserRecord(
            user_id=row.user_id,
            username=row.username,
            password_hash=row.password_hash,
            role=row.role,
        )


if __name__ == "__main__":
    import asyncio

    from agent_service.core.constants import DEFAULT_DATABASE_URL
    from agent_service.memory.database import DatabaseEngineProvider

    async def _demo() -> None:
        # Butuh `docker compose up -d postgres` dan `uv run python -m agent_service.run_migrate`.
        async with DatabaseEngineProvider(DEFAULT_DATABASE_URL) as engine:
            print(await UserRepository(engine).get_by_username("demo"))

    asyncio.run(_demo(), loop_factory=asyncio.SelectorEventLoop)
