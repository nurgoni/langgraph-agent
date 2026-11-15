"""Endpoint `/auth/login`: tukar username dan password dengan access token (FR-33)."""

from fastapi import APIRouter

from agent_service.schema.auth import LoginRequest, TokenResponse
from agent_service.service.dependencies import AuthenticatorDep

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(login_request: LoginRequest, authenticator: AuthenticatorDep) -> TokenResponse:
    """Terbitkan access token JWT. Username atau password salah → 401 dengan pesan yang sama.

    Akun dibuat lewat CLI: `uv run python -m agent_service.manage create-user <username>`.
    """
    return await authenticator.login(login_request.username, login_request.password)
