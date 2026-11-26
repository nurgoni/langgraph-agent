"""Endpoint `/stream`: jalankan agent dan alirkan hasilnya sebagai SSE (FR-7)."""

import logging
from typing import Any, Final

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agent_service.agents.registry import AgentRegistry
from agent_service.memory.traces import RunTraceRepository
from agent_service.schema.requests import StreamInput
from agent_service.service.artifacts import ArtifactService
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
from agent_service.service.streaming import StreamService
from agent_service.service.tracing import RunTraceCollector

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agents"])

SSE_MEDIA_TYPE: Final = "text/event-stream"
# Any: bentuk bebas objek OpenAPI milik FastAPI.
SSE_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    200: {
        "content": {SSE_MEDIA_TYPE: {}},
        "description": "SSE frames, see contracts/stream-event.schema.json.",
        "headers": RUN_RESPONSE_HEADERS,
    }
}


@router.post("/stream", response_class=StreamingResponse, responses=SSE_RESPONSES)
async def stream_default_agent(
    stream_input: StreamInput,
    principal: PrincipalDep,
    registry: RegistryDep,
    traces: TraceRepositoryDep,
    artifacts: ArtifactServiceDep,
    settings: SettingsDep,
    default_agent_id: DefaultAgentIdDep,
) -> StreamingResponse:
    """Sama dengan `POST /{agent_id}/stream` untuk agent default."""
    target = RunTarget(default_agent_id, stream_input.model, settings.agent_recursion_limit)
    return await stream(target, stream_input, principal.user_id, registry, traces, artifacts)


@router.post("/{agent_id}/stream", response_class=StreamingResponse, responses=SSE_RESPONSES)
async def stream_agent(
    agent_id: str,
    stream_input: StreamInput,
    principal: PrincipalDep,
    registry: RegistryDep,
    traces: TraceRepositoryDep,
    artifacts: ArtifactServiceDep,
    settings: SettingsDep,
) -> StreamingResponse:
    """Alirkan frame `token`, `message`, dan `error`, selalu diakhiri `data: [DONE]`.

    Header `X-Thread-Id` berisi ID thread yang dipakai run, sama seperti `/invoke`.
    """
    target = RunTarget(agent_id, stream_input.model, settings.agent_recursion_limit)
    return await stream(target, stream_input, principal.user_id, registry, traces, artifacts)


async def stream(
    target: RunTarget,
    stream_input: StreamInput,
    user_id: str,
    registry: AgentRegistry,
    traces: RunTraceRepository,
    artifacts: ArtifactService,
) -> StreamingResponse:
    """Validasi request lalu mulai stream.

    Semua validasi terjadi sebelum response dimulai, jadi kesalahan request tetap dijawab dengan
    status HTTP yang tepat, bukan frame `error`.

    Args:
        target: Agent, model, batas token, dan project untuk run ini.
        stream_input: Body request.
        user_id: Pemilik run, dari access token.
        registry: Registry agent milik app.
        artifacts: Lampiran pesan (F35).
        traces: Tempat trace run disimpan setelah stream selesai.

    Returns:
        Response SSE.

    Raises:
        AgentNotFoundError: Agent tidak terdaftar (404).
        AgentUnavailableError: Agent gagal dimuat (503).
        UnknownModelError: Model di luar allowlist (422).
        RequestValidationError: `agent_config` tidak valid (422).
        ThreadNotFoundError: Thread milik user, agent, atau project lain (404).
        ArtifactNotFoundError: Lampiran tidak ada atau milik user lain (404).
        ArtifactThreadConflictError: Lampiran sudah tertaut ke thread lain (409).
    """
    agent = registry.get_agent(target.agent_id)
    graph = registry.get_graph(target.agent_id, target.model, target.max_tokens)
    run = await build_attached_run_input(stream_input, user_id, agent, graph, target, artifacts)
    logger.info(
        "Stream agent=%s project=%s run_id=%s thread_id=%s",
        target.agent_id,
        target.project_id,
        run.run_id,
        run.thread_id,
    )
    tracer = RunTraceCollector(traces, run, target.agent_id, target.project_id)
    service = StreamService(graph, run.with_callbacks(tracer), stream_input.stream_tokens, tracer)
    return StreamingResponse(
        service.stream(), media_type=SSE_MEDIA_TYPE, headers=run.response_headers()
    )
