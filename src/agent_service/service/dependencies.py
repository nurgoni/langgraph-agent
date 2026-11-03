"""Dependency FastAPI yang membaca objek service dari `app.state` dengan tipe yang jelas.

>>> from types import SimpleNamespace
>>> app = SimpleNamespace(state=SimpleNamespace(default_agent_id="chatbot"))
>>> get_default_agent_id(Request({"type": "http", "app": app}))
'chatbot'
"""

from typing import Annotated

from fastapi import Depends, Request

from agent_service.agents.registry import AgentRegistry
from agent_service.core.settings import Settings
from agent_service.llm.factory import ModelFactory


def get_settings(request: Request) -> Settings:
    """Ambil `Settings` milik app yang sedang melayani request."""
    return request.app.state.settings


def get_registry(request: Request) -> AgentRegistry:
    """Ambil `AgentRegistry` yang dibuat di lifespan."""
    return request.app.state.registry


def get_model_factory(request: Request) -> ModelFactory:
    """Ambil `ModelFactory` yang dibuat di lifespan."""
    return request.app.state.model_factory


def get_default_agent_id(request: Request) -> str:
    """Ambil ID agent default milik app."""
    return request.app.state.default_agent_id


SettingsDep = Annotated[Settings, Depends(get_settings)]
RegistryDep = Annotated[AgentRegistry, Depends(get_registry)]
ModelFactoryDep = Annotated[ModelFactory, Depends(get_model_factory)]
DefaultAgentIdDep = Annotated[str, Depends(get_default_agent_id)]
