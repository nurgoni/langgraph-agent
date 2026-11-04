"""Endpoint `/stream`: jalankan agent dan alirkan hasilnya sebagai SSE (FR-7)."""

import logging
from typing import Any, Final

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agent_service.agents.registry import AgentRegistry
from agent_service.schema.requests import StreamInput
from agent_service.service.dependencies import DefaultAgentIdDep, RegistryDep
from agent_service.service.run_input import build_run_input
from agent_service.service.streaming import StreamService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agents"])

SSE_MEDIA_TYPE: Final = "text/event-stream"
# Any: bentuk bebas objek OpenAPI milik FastAPI.
SSE_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    200: {"content": {SSE_MEDIA_TYPE: {}}, "description": "Frame SSE."}
}


@router.post("/stream", response_class=StreamingResponse, responses=SSE_RESPONSES)
async def stream_default_agent(
    stream_input: StreamInput, registry: RegistryDep, default_agent_id: DefaultAgentIdDep
) -> StreamingResponse:
    """Sama dengan `POST /{agent_id}/stream` untuk agent default."""
    return await stream(default_agent_id, stream_input, registry)


@router.post("/{agent_id}/stream", response_class=StreamingResponse, responses=SSE_RESPONSES)
async def stream_agent(
    agent_id: str, stream_input: StreamInput, registry: RegistryDep
) -> StreamingResponse:
    """Alirkan frame `token`, `message`, dan `error`, selalu diakhiri `data: [DONE]`.

    Header `X-Thread-Id` dan `X-User-Id` berisi ID yang dipakai run, sama seperti `/invoke`.
    """
    return await stream(agent_id, stream_input, registry)


async def stream(
    agent_id: str, stream_input: StreamInput, registry: AgentRegistry
) -> StreamingResponse:
    """Validasi request lalu mulai stream.

    Semua validasi terjadi sebelum response dimulai, jadi kesalahan request tetap dijawab dengan
    status HTTP yang tepat, bukan frame `error`.

    Args:
        agent_id: Agent tujuan.
        stream_input: Body request.
        registry: Registry agent milik app.

    Returns:
        Response SSE.

    Raises:
        AgentNotFoundError: Agent tidak terdaftar (404).
        AgentUnavailableError: Agent gagal dimuat (503).
        UnknownModelError: Model di luar allowlist (422).
        RequestValidationError: `agent_config` tidak valid (422).
        ThreadNotFoundError: Thread milik user atau agent lain (404).
    """
    agent = registry.get_agent(agent_id)
    graph = registry.get_graph(agent_id, stream_input.model)
    run = await build_run_input(stream_input, agent, graph)
    logger.info("Stream agent=%s run_id=%s thread_id=%s", agent_id, run.run_id, run.thread_id)
    service = StreamService(graph, run, stream_input.stream_tokens)
    return StreamingResponse(
        service.stream(), media_type=SSE_MEDIA_TYPE, headers=run.response_headers()
    )
