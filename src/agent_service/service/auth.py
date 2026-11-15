"""Auth per user (FR-33): hash password argon2 dan access token JWT HS256.

Token stateless: hanya tanda tangan dan kedaluwarsa yang diperiksa, tanpa query database per
request (keputusan user). Klaim `sub` berisi `user_id`, dan `role` berisi `user` atau `service`.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from agent_service.memory.users import USER_ROLES, UserRecord, UserRepository, UserRole
from agent_service.schema.auth import TokenResponse

logger = logging.getLogger(__name__)

JWT_ALGORITHM: Final = "HS256"
SUBJECT_CLAIM: Final = "sub"
ROLE_CLAIM: Final = "role"
REQUIRED_CLAIMS: Final = (SUBJECT_CLAIM, ROLE_CLAIM, "exp", "iat")
INVALID_CREDENTIALS_DETAIL: Final = "Invalid username or password"
INVALID_TOKEN_DETAIL: Final = "Invalid or missing bearer token"
# Dipakai saat username tidak ada, supaya waktu respons sama dengan password yang salah.
TIMING_DUMMY_PASSWORD: Final = "timing-equalizer"


class AuthenticationError(Exception):
    """Dasar error auth. Dipetakan ke 401 dengan header `WWW-Authenticate: Bearer`."""


class InvalidCredentialsError(AuthenticationError):
    """Username tidak ada atau password salah. Pesannya sama untuk keduanya."""

    def __init__(self) -> None:
        """Inisialisasi error dengan pesan yang tidak membedakan penyebabnya."""
        super().__init__(INVALID_CREDENTIALS_DETAIL)


class InvalidTokenError(AuthenticationError):
    """Token tidak ada, rusak, salah tanda tangan, atau kedaluwarsa."""

    def __init__(self) -> None:
        """Inisialisasi error dengan pesan generik, tanpa membocorkan penyebabnya."""
        super().__init__(INVALID_TOKEN_DETAIL)


@dataclass(frozen=True)
class Principal:
    """Pemilik request yang sudah diautentikasi."""

    user_id: str
    role: UserRole


def utc_now() -> datetime:
    """Waktu sekarang dalam UTC. Dipisah supaya test bisa memakai jam tiruan."""
    return datetime.now(UTC)


def hash_password(password: str) -> str:
    """Hash password dengan argon2id (parameter default argon2-cffi).

    >>> hash_password("rahasia123").startswith("$argon2id$")
    True
    """
    return PasswordHasher().hash(password)


class Authenticator:
    """Login dengan username/password, menerbitkan token, dan memverifikasi token.

    Dibuat sekali di lifespan dan disimpan di `app.state.authenticator`.
    """

    def __init__(
        self,
        users: UserRepository,
        jwt_secret: str,
        ttl_seconds: int,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """Inisialisasi authenticator.

        Args:
            users: Repository akun login.
            jwt_secret: Kunci HMAC untuk menandatangani token (`JWT_SECRET`).
            ttl_seconds: Umur token (`JWT_TTL_SECONDS`).
            clock: Sumber waktu untuk klaim `iat`/`exp`.
        """
        self._users = users
        self._jwt_secret = jwt_secret
        self._ttl = timedelta(seconds=ttl_seconds)
        self._clock = clock
        self._hasher = PasswordHasher()
        self._timing_dummy_hash = self._hasher.hash(TIMING_DUMMY_PASSWORD)

    async def login(self, username: str, password: str) -> TokenResponse:
        """Verifikasi password lalu terbitkan access token.

        Args:
            username: Username yang sudah dinormalisasi (huruf kecil).
            password: Password asli dari request.

        Returns:
            Access token beserta identitas user.

        Raises:
            InvalidCredentialsError: Jika username tidak ada atau password salah.
        """
        user = await self._users.get_by_username(username)
        password_hash = self._timing_dummy_hash if user is None else user.password_hash
        password_matches = self._verify_password(password_hash, password)
        if user is None or not password_matches:
            logger.info("Rejected login for username %r", username)
            raise InvalidCredentialsError()
        return self.issue_token(user)

    def issue_token(self, user: UserRecord) -> TokenResponse:
        """Terbitkan access token untuk akun, tanpa memeriksa password.

        Dipakai `login`, dan oleh test untuk membuat token user tanpa menyimpan akun.
        """
        issued_at = self._clock()
        claims = {
            SUBJECT_CLAIM: user.user_id,
            ROLE_CLAIM: user.role,
            "iat": issued_at,
            "exp": issued_at + self._ttl,
        }
        token = jwt.encode(claims, self._jwt_secret, algorithm=JWT_ALGORITHM)
        return TokenResponse(
            access_token=token,
            expires_in=int(self._ttl.total_seconds()),
            user_id=user.user_id,
            username=user.username,
            role=user.role,
        )

    def verify_token(self, token: str) -> Principal:
        """Periksa tanda tangan, kedaluwarsa, dan klaim wajib token.

        Raises:
            InvalidTokenError: Jika token tidak valid karena alasan apa pun.
        """
        try:
            claims = jwt.decode(
                token,
                self._jwt_secret,
                algorithms=[JWT_ALGORITHM],
                options={"require": list(REQUIRED_CLAIMS)},
            )
        except jwt.InvalidTokenError as error:
            logger.debug("Rejected token: %s", error)
            raise InvalidTokenError() from error
        return _principal_from_claims(claims)

    def _verify_password(self, password_hash: str, password: str) -> bool:
        """Bandingkan password dengan hash argon2. Hash rusak dianggap tidak cocok."""
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False


def _principal_from_claims(claims: dict[str, object]) -> Principal:
    """Ubah klaim token menjadi `Principal`.

    Raises:
        InvalidTokenError: Jika `sub` bukan string atau `role` tidak dikenal.
    """
    user_id = claims.get(SUBJECT_CLAIM)
    role = claims.get(ROLE_CLAIM)
    if not isinstance(user_id, str) or role not in USER_ROLES:
        raise InvalidTokenError()
    return Principal(user_id=user_id, role="service" if role == "service" else "user")
