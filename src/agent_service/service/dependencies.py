"""Dependency FastAPI yang membaca objek service dari `app.state` dengan tipe yang jelas.

>>> from types import SimpleNamespace
>>> app = SimpleNamespace(state=SimpleNamespace(default_agent_id="chatbot"))
>>> get_default_agent_id(Request({"type": "http", "app": app}))
'chatbot'
"""

from fastapi import Request

from agent_service.agents.registry import AgentRegistry
from agent_service.core.settings import Settings


def get_settings(request: Request) -> Settings:
    """Ambil `Settings` milik app yang sedang melayani request."""
    return request.app.state.settings


def get_registry(request: Request) -> AgentRegistry:
    """Ambil `AgentRegistry` yang dibuat di lifespan."""
    return request.app.state.registry


def get_default_agent_id(request: Request) -> str:
    """Ambil ID agent default milik app."""
    return request.app.state.default_agent_id
