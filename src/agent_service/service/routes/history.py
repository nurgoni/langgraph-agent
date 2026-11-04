"""Endpoint `/history`: riwayat message satu thread milik user (FR-8)."""

from fastapi import APIRouter
from langchain_core.runnables import RunnableConfig

from agent_service.agents.registry import AgentRegistry
from agent_service.schema.requests import ChatHistoryInput
from agent_service.schema.responses import ChatHistory
from agent_service.service.converters import state_to_chat_messages
from agent_service.service.dependencies import DefaultAgentIdDep, RegistryDep
from agent_service.service.thread_access import ensure_thread_owner

router = APIRouter(tags=["agents"])


@router.post("/history")
async def history_default_agent(
    history_input: ChatHistoryInput, registry: RegistryDep, default_agent_id: DefaultAgentIdDep
) -> ChatHistory:
    """Sama dengan `POST /{agent_id}/history` untuk agent default."""
    return await read_history(default_agent_id, history_input, registry)


@router.post("/{agent_id}/history")
async def history_agent(
    agent_id: str, history_input: ChatHistoryInput, registry: RegistryDep
) -> ChatHistory:
    """Kembalikan semua message thread, urut kronologis. Thread milik user lain → 404."""
    return await read_history(agent_id, history_input, registry)


async def read_history(
    agent_id: str, history_input: ChatHistoryInput, registry: AgentRegistry
) -> ChatHistory:
    """Baca state terakhir thread dan ubah channel `messages` menjadi `ChatMessage`.

    Args:
        agent_id: Agent pemilik thread.
        history_input: ID thread dan user yang meminta.
        registry: Registry agent milik app.

    Returns:
        Riwayat thread.

    Raises:
        AgentNotFoundError: Agent tidak terdaftar (404).
        AgentUnavailableError: Agent gagal dimuat (503).
        ThreadNotFoundError: Thread tidak ada, atau milik user/agent lain (404).
    """
    # Semua graph agent berbagi checkpointer, jadi graph model default cukup untuk membaca state.
    graph = registry.get_graph(agent_id)
    config = RunnableConfig(configurable={"thread_id": history_input.thread_id})
    snapshot = await graph.aget_state(config)
    ensure_thread_owner(snapshot.metadata, history_input.thread_id, history_input.user_id, agent_id)
    return ChatHistory(messages=state_to_chat_messages(snapshot.values))
