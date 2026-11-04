"""Endpoint `/threads`: daftar thread milik user untuk satu agent (FR-9)."""

from typing import Annotated

from fastapi import APIRouter, Query

from agent_service.agents.registry import AgentRegistry
from agent_service.schema.requests import UserThreadsQuery
from agent_service.schema.responses import UserThreads
from agent_service.service.dependencies import (
    DefaultAgentIdDep,
    RegistryDep,
    ThreadRepositoryDep,
)
from agent_service.service.threads import ThreadRepository

router = APIRouter(tags=["threads"])

ThreadsQuery = Annotated[UserThreadsQuery, Query()]


@router.get("/threads")
async def threads_default_agent(
    query: ThreadsQuery,
    registry: RegistryDep,
    repository: ThreadRepositoryDep,
    default_agent_id: DefaultAgentIdDep,
) -> UserThreads:
    """Sama dengan `GET /{agent_id}/threads` untuk agent default."""
    return await list_user_threads(default_agent_id, query, registry, repository)


@router.get("/{agent_id}/threads")
async def threads_agent(
    agent_id: str, query: ThreadsQuery, registry: RegistryDep, repository: ThreadRepositoryDep
) -> UserThreads:
    """Thread milik `user_id` untuk agent ini, yang terakhir di-update lebih dulu.

    `limit` berada di rentang 1–100 (default 20). Nilai di luar rentang menghasilkan 422.
    """
    return await list_user_threads(agent_id, query, registry, repository)


async def list_user_threads(
    agent_id: str,
    query: UserThreadsQuery,
    registry: AgentRegistry,
    repository: ThreadRepository,
) -> UserThreads:
    """Daftar thread user setelah memastikan agent terdaftar.

    Args:
        agent_id: Agent di URL.
        query: `user_id` dan `limit`.
        registry: Registry agent milik app.
        repository: Sumber ringkasan thread.

    Returns:
        Thread milik user.

    Raises:
        AgentNotFoundError: Agent tidak terdaftar (404).
    """
    registry.get_agent(agent_id)
    threads = await repository.list_threads(query.user_id, agent_id, query.limit)
    return UserThreads(threads=threads)
