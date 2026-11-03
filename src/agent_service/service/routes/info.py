"""Endpoint `/info`: agent, model, dan nilai default service (FR-5)."""

from fastapi import APIRouter

from agent_service.schema.responses import ServiceMetadata
from agent_service.service.converters import agent_to_info
from agent_service.service.dependencies import (
    DefaultAgentIdDep,
    ModelFactoryDep,
    RegistryDep,
    SettingsDep,
)

router = APIRouter(tags=["info"])


@router.get("/info")
async def info(
    settings: SettingsDep,
    registry: RegistryDep,
    model_factory: ModelFactoryDep,
    default_agent_id: DefaultAgentIdDep,
) -> ServiceMetadata:
    """Daftar agent yang siap dipakai beserta JSON Schema config-nya, dan daftar model.

    Agent yang gagal dimuat tidak ditampilkan, supaya client tidak menawarkan agent yang pasti
    menjawab 503.
    """
    agents = [
        agent_to_info(agent)
        for agent in registry.list_agents()
        if registry.is_available(agent.agent_id)
    ]
    return ServiceMetadata(
        agents=agents,
        models=list(settings.available_models),
        default_agent=default_agent_id,
        default_model=model_factory.resolve_name(),
    )
