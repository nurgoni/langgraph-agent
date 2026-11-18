"""Endpoint `/projects`: CRUD project dan chat di dalam project (FR-36, ADR 0004).

Chat di project memakai route `/projects/{project_id}/...` (keputusan user, PRD §11 no. 8).
Agent ditentukan project (`base_agent_id`). Model: request → project → default service.
"""

from fastapi import APIRouter, Response, status
from fastapi.responses import StreamingResponse

from agent_service.memory.projects import ProjectRecord
from agent_service.schema.projects import Project, ProjectCreate, ProjectList, ProjectUpdate
from agent_service.schema.requests import (
    ChatHistoryInput,
    StreamInput,
    ThreadRenameInput,
    UserInput,
)
from agent_service.schema.responses import ChatHistory, ChatMessage, ThreadSummary, UserThreads
from agent_service.service.dependencies import (
    ArtifactServiceDep,
    PrincipalDep,
    ProjectServiceDep,
    RegistryDep,
    ThreadRepositoryDep,
    TraceRepositoryDep,
)
from agent_service.service.projects import project_max_tokens, project_to_schema, run_context
from agent_service.service.routes.history import read_history
from agent_service.service.routes.invoke import INVOKE_RESPONSES, invoke
from agent_service.service.routes.stream import SSE_RESPONSES, stream
from agent_service.service.routes.threads import ThreadsQuery
from agent_service.service.run_input import RunTarget

router = APIRouter(prefix="/projects", tags=["projects"])


def run_target(record: ProjectRecord, requested_model: str | None) -> RunTarget:
    """Target run di project: agent dasar, model request atau project, dan batas token project."""
    return RunTarget(
        agent_id=record.base_agent_id,
        model=requested_model if requested_model is not None else record.model,
        max_tokens=project_max_tokens(record),
        project=run_context(record),
    )


@router.get("")
async def list_projects(principal: PrincipalDep, projects: ProjectServiceDep) -> ProjectList:
    """Project built-in, lalu project milik user (terbaru diubah dulu)."""
    return ProjectList(projects=await projects.list_visible(principal.user_id))


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(
    project_create: ProjectCreate, principal: PrincipalDep, projects: ProjectServiceDep
) -> Project:
    """Buat project milik user. Agent atau model yang tidak dikenal → 422."""
    return await projects.create(principal.user_id, project_create)


@router.get("/{project_id}")
async def get_project(
    project_id: str, principal: PrincipalDep, projects: ProjectServiceDep
) -> Project:
    """Satu project built-in atau milik user. Project milik user lain → 404."""
    return project_to_schema(await projects.get_visible(project_id, principal.user_id))


@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    project_update: ProjectUpdate,
    principal: PrincipalDep,
    projects: ProjectServiceDep,
) -> Project:
    """Ubah field yang dikirim saja. Project built-in → 403."""
    return await projects.update(project_id, principal.user_id, project_update)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str, principal: PrincipalDep, projects: ProjectServiceDep
) -> None:
    """Hapus project beserta semua thread di dalamnya. Project built-in → 403."""
    await projects.delete(project_id, principal.user_id)


@router.post("/{project_id}/invoke", responses=INVOKE_RESPONSES)
async def invoke_in_project(
    project_id: str,
    user_input: UserInput,
    response: Response,
    principal: PrincipalDep,
    projects: ProjectServiceDep,
    registry: RegistryDep,
    traces: TraceRepositoryDep,
    artifacts: ArtifactServiceDep,
) -> ChatMessage:
    """Jalankan agent project sampai selesai, dengan instruksi dan pengaturan project."""
    record = await projects.get_visible(project_id, principal.user_id)
    target = run_target(record, user_input.model)
    return await invoke(
        target, user_input, principal.user_id, response, registry, traces, artifacts
    )


@router.post("/{project_id}/stream", response_class=StreamingResponse, responses=SSE_RESPONSES)
async def stream_in_project(
    project_id: str,
    stream_input: StreamInput,
    principal: PrincipalDep,
    projects: ProjectServiceDep,
    registry: RegistryDep,
    traces: TraceRepositoryDep,
    artifacts: ArtifactServiceDep,
) -> StreamingResponse:
    """Alirkan run agent project sebagai SSE, sama seperti `/{agent_id}/stream`."""
    record = await projects.get_visible(project_id, principal.user_id)
    target = run_target(record, stream_input.model)
    return await stream(target, stream_input, principal.user_id, registry, traces, artifacts)


@router.post("/{project_id}/history")
async def project_history(
    project_id: str,
    history_input: ChatHistoryInput,
    principal: PrincipalDep,
    projects: ProjectServiceDep,
    registry: RegistryDep,
) -> ChatHistory:
    """Riwayat satu thread di project ini. Thread di luar project ini → 404."""
    record = await projects.get_visible(project_id, principal.user_id)
    return await read_history(
        record.base_agent_id, history_input, principal.user_id, registry, project_id
    )


@router.get("/{project_id}/threads")
async def project_threads(
    project_id: str,
    query: ThreadsQuery,
    principal: PrincipalDep,
    projects: ProjectServiceDep,
    threads: ThreadRepositoryDep,
) -> UserThreads:
    """Thread milik user di project ini, yang terakhir di-update lebih dulu."""
    record = await projects.get_visible(project_id, principal.user_id)
    summaries = await threads.list_threads(
        principal.user_id, record.base_agent_id, query.limit, project_id
    )
    return UserThreads(threads=summaries)


@router.patch("/{project_id}/threads/{thread_id}")
async def rename_project_thread(
    project_id: str,
    thread_id: str,
    rename_input: ThreadRenameInput,
    principal: PrincipalDep,
    projects: ProjectServiceDep,
    threads: ThreadRepositoryDep,
) -> ThreadSummary:
    """Ganti judul thread di project ini."""
    record = await projects.get_visible(project_id, principal.user_id)
    return await threads.rename(
        thread_id, principal.user_id, record.base_agent_id, rename_input.title, project_id
    )


@router.delete("/{project_id}/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_thread(
    project_id: str,
    thread_id: str,
    principal: PrincipalDep,
    projects: ProjectServiceDep,
    threads: ThreadRepositoryDep,
) -> None:
    """Hapus satu thread di project ini beserta riwayatnya."""
    record = await projects.get_visible(project_id, principal.user_id)
    await threads.delete(thread_id, principal.user_id, record.base_agent_id, project_id)
