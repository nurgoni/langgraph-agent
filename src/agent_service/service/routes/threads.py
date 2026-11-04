"""Endpoint `/threads`: daftar, rename, dan hapus thread milik user (FR-9, FR-25, FR-26)."""

from typing import Annotated

from fastapi import APIRouter, Query

from agent_service.agents.registry import AgentRegistry
from agent_service.schema.requests import ThreadRenameInput, UserThreadsQuery
from agent_service.schema.responses import ThreadSummary, UserThreads
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


@router.patch("/threads/{thread_id}")
async def rename_thread_default_agent(
    thread_id: str,
    rename_input: ThreadRenameInput,
    registry: RegistryDep,
    repository: ThreadRepositoryDep,
    default_agent_id: DefaultAgentIdDep,
) -> ThreadSummary:
    """Sama dengan `PATCH /{agent_id}/threads/{thread_id}` untuk agent default."""
    return await rename_user_thread(default_agent_id, thread_id, rename_input, registry, repository)


@router.patch("/{agent_id}/threads/{thread_id}")
async def rename_thread_agent(
    agent_id: str,
    thread_id: str,
    rename_input: ThreadRenameInput,
    registry: RegistryDep,
    repository: ThreadRepositoryDep,
) -> ThreadSummary:
    """Ganti judul thread. Hanya pemilik thread yang boleh. Thread milik user lain → 404."""
    return await rename_user_thread(agent_id, thread_id, rename_input, registry, repository)


async def rename_user_thread(
    agent_id: str,
    thread_id: str,
    rename_input: ThreadRenameInput,
    registry: AgentRegistry,
    repository: ThreadRepository,
) -> ThreadSummary:
    """Rename thread setelah memastikan agent terdaftar.

    Raises:
        AgentNotFoundError: Agent tidak terdaftar (404).
        ThreadNotFoundError: Thread tidak ada, atau milik user/agent lain (404).
    """
    registry.get_agent(agent_id)
    return await repository.rename(thread_id, rename_input.user_id, agent_id, rename_input.title)
