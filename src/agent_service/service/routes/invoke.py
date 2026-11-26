"""Endpoint `/invoke`: jalankan agent sampai selesai dan kembalikan jawaban akhir (FR-6)."""

import logging
from typing import Any, Final

from fastapi import APIRouter, Response
from langgraph.errors import GraphRecursionError

from agent_service.agents.errors import AgentStepLimitError
from agent_service.agents.registry import AgentRegistry
from agent_service.memory.traces import RunTraceRepository
from agent_service.schema.requests import UserInput
from agent_service.schema.responses import ChatMessage
from agent_service.service.artifacts import ArtifactService
from agent_service.service.converters import INTERRUPT_KEY, final_chat_message
from agent_service.service.dependencies import (
    ArtifactServiceDep,
    DefaultAgentIdDep,
    PrincipalDep,
    RegistryDep,
    SettingsDep,
    TraceRepositoryDep,
)
from agent_service.service.run_input import (
    RUN_RESPONSE_HEADERS,
    RunTarget,
    build_attached_run_input,
)
from agent_service.service.tracing import RunTraceCollector

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agents"])

# Any: bentuk bebas objek OpenAPI milik FastAPI.
INVOKE_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {200: {"headers": RUN_RESPONSE_HEADERS}}


@router.post("/invoke", responses=INVOKE_RESPONSES)
async def invoke_default_agent(
    user_input: UserInput,
    response: Response,
    principal: PrincipalDep,
    registry: RegistryDep,
    traces: TraceRepositoryDep,
    artifacts: ArtifactServiceDep,
    settings: SettingsDep,
    default_agent_id: DefaultAgentIdDep,
) -> ChatMessage:
    """Sama dengan `POST /{agent_id}/invoke` untuk agent default."""
    target = RunTarget(default_agent_id, user_input.model, settings.agent_recursion_limit)
    return await invoke(
        target, user_input, principal.user_id, response, registry, traces, artifacts
    )


@router.post("/{agent_id}/invoke", responses=INVOKE_RESPONSES)
async def invoke_agent(
    agent_id: str,
    user_input: UserInput,
    response: Response,
    principal: PrincipalDep,
    registry: RegistryDep,
    traces: TraceRepositoryDep,
    artifacts: ArtifactServiceDep,
    settings: SettingsDep,
) -> ChatMessage:
    """Jalankan agent dan kembalikan message terakhirnya, atau pertanyaan interrupt.

    Header `X-Thread-Id` berisi ID thread yang dipakai run, untuk melanjutkan thread.
    """
    target = RunTarget(agent_id, user_input.model, settings.agent_recursion_limit)
    return await invoke(
        target, user_input, principal.user_id, response, registry, traces, artifacts
    )


async def invoke(
    target: RunTarget,
    user_input: UserInput,
    user_id: str,
    response: Response,
    registry: AgentRegistry,
    traces: RunTraceRepository,
    artifacts: ArtifactService,
) -> ChatMessage:
    """Jalankan satu run agent sampai selesai, dan simpan trace-nya (FR-41).

    Args:
        target: Agent, model, batas token, dan project untuk run ini.
        user_input: Body request.
        user_id: Pemilik run, dari access token.
        response: Response FastAPI, untuk header ID thread.
        registry: Registry agent milik app.
        artifacts: Lampiran pesan (F35).
        traces: Tempat trace run disimpan.

    Returns:
        Jawaban akhir dengan `run_id` terisi.

    Raises:
        AgentNotFoundError: Agent tidak terdaftar (404).
        AgentUnavailableError: Agent gagal dimuat (503).
        UnknownModelError: Model di luar allowlist (422).
        RequestValidationError: `agent_config` tidak valid (422).
        ThreadNotFoundError: Thread milik user, agent, atau project lain (404).
        ArtifactNotFoundError: Lampiran tidak ada atau milik user lain (404).
        ArtifactThreadConflictError: Lampiran sudah tertaut ke thread lain (409).
        AgentStepLimitError: Run melewati `recursion_limit` (500, FR-59).
    """
    agent = registry.get_agent(target.agent_id)
    graph = registry.get_graph(target.agent_id, target.model, target.max_tokens)
    run = await build_attached_run_input(user_input, user_id, agent, graph, target, artifacts)
    logger.info(
        "Invoke agent=%s project=%s run_id=%s thread_id=%s",
        target.agent_id,
        target.project_id,
        run.run_id,
        run.thread_id,
    )
    tracer = RunTraceCollector(traces, run, target.agent_id, target.project_id)
    traced = run.with_callbacks(tracer)
    try:
        state = await graph.ainvoke(traced.graph_input, traced.config, context=traced.context)
    except GraphRecursionError as error:
        await tracer.save("error", error)
        raise AgentStepLimitError(target.agent_id) from error
    # Bukan penanganan error: trace run yang gagal disimpan, lalu error diteruskan ke handler.
    except Exception as error:
        await tracer.save("error", error)
        raise
    await tracer.save("interrupted" if state.get(INTERRUPT_KEY) else "ok")
    response.headers.update(run.response_headers())
    return final_chat_message(state).model_copy(update={"run_id": str(run.run_id)})
