"""Endpoint `/invoke`: jalankan agent sampai selesai dan kembalikan jawaban akhir (FR-6)."""

import logging

from fastapi import APIRouter, Response

from agent_service.agents.registry import AgentRegistry
from agent_service.schema.requests import UserInput
from agent_service.schema.responses import ChatMessage
from agent_service.service.converters import final_chat_message
from agent_service.service.dependencies import DefaultAgentIdDep, PrincipalDep, RegistryDep
from agent_service.service.run_input import build_run_input

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agents"])


@router.post("/invoke")
async def invoke_default_agent(
    user_input: UserInput,
    response: Response,
    principal: PrincipalDep,
    registry: RegistryDep,
    default_agent_id: DefaultAgentIdDep,
) -> ChatMessage:
    """Sama dengan `POST /{agent_id}/invoke` untuk agent default."""
    return await invoke(default_agent_id, user_input, principal.user_id, response, registry)


@router.post("/{agent_id}/invoke")
async def invoke_agent(
    agent_id: str,
    user_input: UserInput,
    response: Response,
    principal: PrincipalDep,
    registry: RegistryDep,
) -> ChatMessage:
    """Jalankan agent dan kembalikan message terakhirnya, atau pertanyaan interrupt.

    Header `X-Thread-Id` berisi ID thread yang dipakai run, untuk melanjutkan thread.
    """
    return await invoke(agent_id, user_input, principal.user_id, response, registry)


async def invoke(
    agent_id: str,
    user_input: UserInput,
    user_id: str,
    response: Response,
    registry: AgentRegistry,
) -> ChatMessage:
    """Jalankan satu run agent sampai selesai.

    Args:
        agent_id: Agent tujuan.
        user_input: Body request.
        user_id: Pemilik run, dari access token.
        response: Response FastAPI, untuk header ID thread.
        registry: Registry agent milik app.

    Returns:
        Jawaban akhir dengan `run_id` terisi.

    Raises:
        AgentNotFoundError: Agent tidak terdaftar (404).
        AgentUnavailableError: Agent gagal dimuat (503).
        UnknownModelError: Model di luar allowlist (422).
        RequestValidationError: `agent_config` tidak valid (422).
        ThreadNotFoundError: Thread milik user atau agent lain (404).
    """
    agent = registry.get_agent(agent_id)
    graph = registry.get_graph(agent_id, user_input.model)
    run = await build_run_input(user_input, user_id, agent, graph)
    logger.info("Invoke agent=%s run_id=%s thread_id=%s", agent_id, run.run_id, run.thread_id)
    state = await graph.ainvoke(run.graph_input, run.config)
    response.headers.update(run.response_headers())
    return final_chat_message(state).model_copy(update={"run_id": str(run.run_id)})
