"""Dependency FastAPI yang membaca objek service dari `app.state` dengan tipe yang jelas.

>>> from types import SimpleNamespace
>>> app = SimpleNamespace(state=SimpleNamespace(default_agent_id="chatbot"))
>>> get_default_agent_id(Request({"type": "http", "app": app}))
'chatbot'
"""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agent_service.agents.registry import AgentRegistry
from agent_service.core.settings import Settings
from agent_service.llm.factory import ModelFactory
from agent_service.service.auth import Authenticator, InvalidTokenError, Principal
from agent_service.service.projects import ProjectService
from agent_service.service.threads import ThreadRepository

# auto_error=False: header yang hilang dijawab InvalidTokenError (401 + WWW-Authenticate), sama
# seperti token yang salah, bukan 403 bawaan HTTPBearer.
bearer_scheme = HTTPBearer(auto_error=False, description="Access token dari `POST /auth/login`.")


def get_settings(request: Request) -> Settings:
    """Ambil `Settings` milik app yang sedang melayani request."""
    return request.app.state.settings


def get_registry(request: Request) -> AgentRegistry:
    """Ambil `AgentRegistry` yang dibuat di lifespan."""
    return request.app.state.registry


def get_model_factory(request: Request) -> ModelFactory:
    """Ambil `ModelFactory` yang dibuat di lifespan."""
    return request.app.state.model_factory


def get_thread_repository(request: Request) -> ThreadRepository:
    """Ambil `ThreadRepository` yang dibuat di lifespan."""
    return request.app.state.thread_repository


def get_project_service(request: Request) -> ProjectService:
    """Ambil `ProjectService` yang dibuat di lifespan."""
    return request.app.state.project_service


def get_default_agent_id(request: Request) -> str:
    """Ambil ID agent default milik app."""
    return request.app.state.default_agent_id


def get_authenticator(request: Request) -> Authenticator:
    """Ambil `Authenticator` yang dibuat di lifespan."""
    return request.app.state.authenticator


def current_principal(
    authenticator: Annotated[Authenticator, Depends(get_authenticator)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> Principal:
    """User pemilik request, dari header `Authorization: Bearer <token>` (FR-33).

    Dipasang per router di `create_app`, dan diminta lagi oleh route yang butuh `user_id`.
    FastAPI meng-cache dependency per request, jadi token hanya diverifikasi sekali.

    Raises:
        InvalidTokenError: Jika header tidak ada atau token tidak valid (401).
    """
    if credentials is None:
        raise InvalidTokenError()
    return authenticator.verify_token(credentials.credentials)


SettingsDep = Annotated[Settings, Depends(get_settings)]
RegistryDep = Annotated[AgentRegistry, Depends(get_registry)]
ModelFactoryDep = Annotated[ModelFactory, Depends(get_model_factory)]
ThreadRepositoryDep = Annotated[ThreadRepository, Depends(get_thread_repository)]
DefaultAgentIdDep = Annotated[str, Depends(get_default_agent_id)]
AuthenticatorDep = Annotated[Authenticator, Depends(get_authenticator)]
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
PrincipalDep = Annotated[Principal, Depends(current_principal)]
