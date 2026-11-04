"""Auth bearer token bersama (`AUTH_SECRET`) untuk semua route kecuali `/health`."""

import secrets
from typing import Annotated, Final

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agent_service.core.settings import Settings
from agent_service.service.dependencies import get_settings

UNAUTHORIZED_DETAIL: Final = "Invalid or missing bearer token"
BEARER_CHALLENGE: Final = {"WWW-Authenticate": "Bearer"}

# auto_error=False: request tanpa header tetap masuk ke verify_bearer, supaya auth bisa nonaktif
# saat AUTH_SECRET kosong.
bearer_scheme: Final = HTTPBearer(
    auto_error=False, description="Bearer token sesuai AUTH_SECRET service."
)


async def verify_bearer(
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> None:
    """Tolak request yang token-nya tidak cocok dengan `AUTH_SECRET` (FR-11).

    Function, bukan class: ini dependency FastAPI. Jika `AUTH_SECRET` kosong, semua request lolos.
    Token dibandingkan dengan `secrets.compare_digest` agar tidak bocor lewat waktu respons.

    Args:
        settings: Konfigurasi service.
        credentials: Header `Authorization: Bearer <token>`, atau `None` jika tidak ada.

    Raises:
        HTTPException: 401 jika auth aktif dan token tidak ada atau salah.

    >>> import asyncio
    >>> open_settings = Settings(_env_file=None, use_fake_model=True)
    >>> asyncio.run(verify_bearer(open_settings, None)) is None
    True
    """
    if settings.auth_secret is None:
        return
    expected_token = settings.auth_secret.get_secret_value()
    if credentials is not None and secrets.compare_digest(credentials.credentials, expected_token):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=UNAUTHORIZED_DETAIL,
        headers=BEARER_CHALLENGE,
    )
