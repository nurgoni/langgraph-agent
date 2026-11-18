"""Workspace di service (F36): lampiran disalin ke workspace, `publish` untuk `share_file`, dan
pembersihan saat thread dihapus."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.store.base import BaseStore

from agent_service.agents.base import AgentGraph, BaseAgent, Checkpointer
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.agents.tool_calling import ToolCallingAgent
from agent_service.files.workspace import Workspace
from agent_service.harness.context import ContextBuilder
from agent_service.harness.workspace import WorkspaceToolkit
from agent_service.llm.fake import FakeModel
from agent_service.schema.artifacts import ArtifactRef
from agent_service.schema.responses import ChatHistory
from agent_service.service.artifacts import ArtifactService

OWNER = "user-a"
CSV_CONTENT = b"region,total\nnorth,10\n"


def artifact_service(app: FastAPI) -> ArtifactService:
    return app.state.artifact_service


def workspace(app: FastAPI) -> Workspace:
    return artifact_service(app).run_context().workspace


async def upload(client: AsyncClient, filename: str = "sales.csv") -> ArtifactRef:
    response = await client.post("/artifacts", files={"file": (filename, CSV_CONTENT, "text/csv")})
    assert response.status_code == 201, response.text
    return ArtifactRef.model_validate(response.json())


async def send(client: AsyncClient, **body: object) -> str:
    response = await client.post("/invoke", json={"message": "Read this", **body})
    assert response.status_code == 200, response.text
    return response.headers["X-Thread-Id"]


async def test_attachments_are_copied_into_the_thread_workspace(
    client: AsyncClient, app: FastAPI
) -> None:
    artifact = await upload(client)

    thread_id = await send(client, artifact_ids=[artifact.id])

    assert await workspace(app).read(thread_id, "uploads/sales.csv") == CSV_CONTENT
    history = await client.post("/history", json={"thread_id": thread_id})
    human = ChatHistory.model_validate(history.json()).messages[0]
    assert human.content == "Read this"
    assert human.artifacts == [artifact]


async def test_same_file_name_gets_a_marker_instead_of_overwriting(
    client: AsyncClient, app: FastAPI
) -> None:
    first = await upload(client)
    thread_id = await send(client, artifact_ids=[first.id])
    second = await upload(client)

    await send(client, thread_id=thread_id, artifact_ids=[second.id])

    paths = [file.path for file in await workspace(app).list_files(thread_id)]
    assert sorted(paths) == sorted(["uploads/sales.csv", f"uploads/sales-{second.id[:8]}.csv"])


async def test_published_workspace_file_is_a_downloadable_thread_artifact(
    client: AsyncClient, app: FastAPI
) -> None:
    thread_id = await send(client)

    record = await artifact_service(app).publish(OWNER, thread_id, "summary.md", b"# Q3")
    download = await client.get(f"/artifacts/{record.artifact_id}")
    await client.delete(f"/threads/{thread_id}")

    assert (record.thread_id, record.mime_type) == (thread_id, "text/markdown")
    assert download.content == b"# Q3"
    assert (await client.get(f"/artifacts/{record.artifact_id}")).status_code == 404


async def test_deleting_a_thread_clears_its_workspace(client: AsyncClient, app: FastAPI) -> None:
    artifact = await upload(client)
    thread_id = await send(client, artifact_ids=[artifact.id])
    await workspace(app).write(thread_id, "reports/draft.md", b"draft")

    response = await client.delete(f"/threads/{thread_id}")

    assert response.status_code == 204
    assert await workspace(app).list_files(thread_id) == []


async def test_rejected_attachment_request_writes_nothing(
    client: AsyncClient, app: FastAPI
) -> None:
    artifact = await upload(client)
    thread_id = await _interrupted(client)

    answer = await client.post(
        "/interrupt/invoke",
        json={"message": "Budi", "thread_id": thread_id, "artifact_ids": [artifact.id]},
    )

    assert answer.status_code == 422
    assert await workspace(app).list_files(thread_id) == []


async def _interrupted(client: AsyncClient) -> str:
    response = await client.post("/interrupt/invoke", json={"message": "Hi"})
    assert response.status_code == 200, response.text
    return response.headers["X-Thread-Id"]


class FileWritingAgent(BaseAgent):
    """Agent test yang selalu memanggil `write_file`, apa pun model dari registry."""

    def build(
        self, model: BaseChatModel, checkpointer: Checkpointer, store: BaseStore | None = None
    ) -> AgentGraph:
        write = {"name": "write_file", "args": {"path": "out.txt", "content": "hi"}, "id": "w1"}
        scripted = FakeModel(responses=[AIMessage(content="", tool_calls=[write]), "Saved."])
        files = WorkspaceToolkit(output_max_tokens=1000)
        agent = ToolCallingAgent("writer", "Writes", [], ContextBuilder(), files=files)
        return agent.build(scripted, checkpointer)


@pytest.fixture
def agents(interrupt_agent: BaseAgent) -> list[BaseAgent]:
    writer = FileWritingAgent(agent_id="writer", description="Writes a file")
    return [ChatbotAgent(), interrupt_agent, writer]


@pytest.mark.parametrize("route", ["/writer/invoke", "/writer/stream"])
async def test_runs_give_tools_the_thread_workspace(
    client: AsyncClient, app: FastAPI, route: str
) -> None:
    response = await client.post(route, json={"message": "Save it"})

    assert response.status_code == 200, response.text
    thread_id = response.headers["X-Thread-Id"]
    assert await workspace(app).read(thread_id, "out.txt") == b"hi"
