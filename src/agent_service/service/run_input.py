"""Penyusunan input dan config untuk satu run agent dari request `UserInput`."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any, Final
from uuid import UUID, uuid4

from fastapi.exceptions import RequestValidationError
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.utils.uuid import uuid7
from langgraph.types import Command, StateSnapshot
from pydantic import BaseModel, JsonValue, ValidationError

from agent_service.agents.base import AgentGraph, BaseAgent
from agent_service.core.constants import (
    ARTIFACTS_KWARG,
    PROJECT_ID_CONFIG_KEY,
    PROJECT_INSTRUCTIONS_CONFIG_KEY,
    PROJECT_SKILL_IDS_CONFIG_KEY,
    PROJECT_TOOL_APPROVAL_CONFIG_KEY,
    USER_ID_CONFIG_KEY,
    WORKSPACE_FILES_KWARG,
)
from agent_service.harness.runtime import HarnessContext
from agent_service.schema.artifacts import ArtifactRef
from agent_service.schema.headers import THREAD_ID_HEADER
from agent_service.schema.requests import UserInput
from agent_service.service.artifacts import ArtifactService, artifact_ref
from agent_service.service.thread_access import ensure_thread_owner, is_new_thread, run_metadata

AGENT_CONFIG_LOCATION: Final = ("body", "agent_config")
ARTIFACT_IDS_LOCATION: Final = ("body", "artifact_ids")
ATTACHMENTS_ON_INTERRUPT_MESSAGE: Final = "Attachments cannot be sent as an answer to a question"
# Header respons run di OpenAPI, supaya tipe client hasil generate tahu cara membaca ID thread.
# Any: bentuk bebas objek OpenAPI milik FastAPI.
RUN_RESPONSE_HEADERS: Final[dict[str, dict[str, Any]]] = {
    THREAD_ID_HEADER: {
        "description": "Thread used by this run. Send it as `thread_id` to continue the thread.",
        "schema": {"type": "string"},
    }
}

# Any: bentuk input bergantung pada state agent. Command dipakai untuk melanjutkan interrupt.
type GraphInput = dict[str, Any] | Command


@dataclass(frozen=True)
class ProjectRunContext:
    """Konfigurasi project yang ikut ke setiap run di dalamnya (ADR 0004).

    Dibaca dari database di awal setiap run, jadi perubahan project langsung berlaku di giliran
    berikutnya. Isinya diteruskan ke agent lewat `configurable` (dipakai F27/F28).
    """

    project_id: str
    instructions: str = ""
    skill_ids: tuple[str, ...] = ()
    tool_approval: str = "never"

    def configurable(self) -> dict[str, Any]:  # Any: nilai configurable LangGraph
        """Kunci `configurable` untuk project ini.

        >>> config = ProjectRunContext("p1", "Ringkas.", ("meeting-notes",)).configurable()
        >>> config["project_id"], config["project_instructions"], config["project_skill_ids"]
        ('p1', 'Ringkas.', ['meeting-notes'])
        """
        return {
            PROJECT_ID_CONFIG_KEY: self.project_id,
            PROJECT_INSTRUCTIONS_CONFIG_KEY: self.instructions,
            PROJECT_SKILL_IDS_CONFIG_KEY: list(self.skill_ids),
            PROJECT_TOOL_APPROVAL_CONFIG_KEY: self.tool_approval,
        }


@dataclass(frozen=True)
class RunTarget:
    """Agent, model, batas token, dan project untuk satu run.

    Route agent memakai agent dari URL dan model dari request. Route project memakai agent dasar
    project, model request → model project → default, dan `max_tokens` project.

    >>> RunTarget("chatbot").project_id is None
    True
    """

    agent_id: str
    model: str | None = None
    max_tokens: int | None = None
    project: ProjectRunContext | None = None

    @property
    def project_id(self) -> str | None:
        """ID project run ini, atau `None` untuk route agent."""
        return None if self.project is None else self.project.project_id


@dataclass(frozen=True)
class MessageAttachments:
    """Lampiran pesan human: referensi artifact (F35) dan path salinannya di workspace (F36)."""

    references: Sequence[ArtifactRef] = ()
    workspace_paths: Sequence[str] = ()

    def message_kwargs(self) -> dict[str, Any]:  # Any: nilai additional_kwargs LangChain
        """`additional_kwargs` message human untuk lampiran ini.

        >>> ref = ArtifactRef(id="a1", name="a.csv", mime_type="text/csv", size=3)
        >>> sorted(MessageAttachments([ref], ["uploads/a.csv"]).message_kwargs())
        ['artifacts', 'workspace_files']
        """
        kwargs: dict[str, Any] = {ARTIFACTS_KWARG: [ref.model_dump() for ref in self.references]}
        if self.workspace_paths:
            kwargs[WORKSPACE_FILES_KWARG] = list(self.workspace_paths)
        return kwargs


@dataclass(frozen=True)
class RunInput:
    """Semua yang dibutuhkan untuk menjalankan graph satu kali.

    `context` dikirim sebagai runtime context LangGraph (`ainvoke(..., context=...)`), berisi
    workspace dan penerbit artifact untuk tool harness (F36). `None` berarti tanpa workspace.
    """

    graph_input: GraphInput
    config: RunnableConfig
    run_id: UUID
    thread_id: str
    user_id: str
    context: HarnessContext | None = None

    def response_headers(self) -> dict[str, str]:
        """Header yang mengembalikan ID thread ke client (FR-13)."""
        return {THREAD_ID_HEADER: self.thread_id}

    def with_callbacks(self, *handlers: BaseCallbackHandler) -> "RunInput":
        """Salinan run dengan callback di config, misalnya trace (FR-41).

        `build_run_input` tidak memasang callback, jadi daftar ini menjadi seluruh callback run.
        """
        config = RunnableConfig(**self.config)
        config["callbacks"] = list(handlers)
        return replace(self, config=config)


async def build_run_input(
    user_input: UserInput,
    user_id: str,
    agent: BaseAgent,
    graph: AgentGraph,
    project: ProjectRunContext | None = None,
    attachments: MessageAttachments | None = None,
) -> RunInput:
    """Siapkan input graph untuk request, termasuk ID baru dan resume interrupt.

    Function, bukan class: tidak menyimpan state, dan setiap langkah sudah dipecah ke helper.

    Args:
        user_input: Body request `/invoke` atau `/stream`.
        user_id: Pemilik run, dari access token.
        agent: Agent tujuan, untuk validasi `agent_config`.
        graph: Graph agent untuk model yang dipilih.
        project: Project tempat run berjalan, atau `None` untuk route agent.
        attachments: Lampiran yang sudah diperiksa kepemilikannya, untuk pesan human (F35, F36).

    Returns:
        Input dan config run. `thread_id` yang kosong diisi UUID baru (FR-13).

    Raises:
        RequestValidationError: Jika `agent_config` tidak lolos `config_schema` agent, atau ada
            lampiran untuk jawaban interrupt (422).
        ThreadNotFoundError: Jika thread sudah ada tapi milik user, agent, atau project lain (404).
    """
    agent_config = parse_agent_config(agent, user_input.agent_config)
    thread_id = user_input.thread_id or str(uuid4())
    run_id = uuid7()
    configurable: dict[str, Any] = {"thread_id": thread_id, USER_ID_CONFIG_KEY: user_id}
    configurable.update(agent_config.model_dump(mode="json"))
    project_id = None if project is None else project.project_id
    if project is not None:
        configurable.update(project.configurable())
    config = RunnableConfig(
        configurable=configurable,
        metadata=run_metadata(user_id, agent.agent_id, project_id),
        run_id=run_id,
    )
    snapshot = await graph.aget_state(config)
    if not is_new_thread(snapshot):
        ensure_thread_owner(snapshot.metadata, thread_id, user_id, agent.agent_id, project_id)
    return RunInput(
        graph_input=_graph_input_for(snapshot, user_input.message, attachments),
        config=config,
        run_id=run_id,
        thread_id=thread_id,
        user_id=user_id,
    )


async def build_attached_run_input(
    user_input: UserInput,
    user_id: str,
    agent: BaseAgent,
    graph: AgentGraph,
    project: ProjectRunContext | None,
    artifacts: ArtifactService,
) -> RunInput:
    """`build_run_input` dengan lampiran `artifact_ids` dan runtime context tool harness.

    Lampiran diperiksa sebelum run disusun, lalu ditautkan ke thread dan disalin ke workspace-nya
    (`uploads/`) setelah kepemilikan thread lolos, jadi request yang ditolak tidak mengubah
    artifact maupun workspace. Thread baru mendapat ID lebih dulu supaya path salinan bisa dipilih.

    Raises:
        ArtifactNotFoundError: Lampiran tidak ada atau milik user lain (404).
        ArtifactThreadConflictError: Lampiran sudah tertaut ke thread lain (409).
        RequestValidationError: `agent_config` tidak valid, atau lampiran untuk jawaban interrupt
            (422).
        ThreadNotFoundError: Thread milik user, agent, atau project lain (404).
    """
    records = await artifacts.resolve_attachments(
        user_id, user_input.artifact_ids, user_input.thread_id
    )
    if not records:
        run = await build_run_input(user_input, user_id, agent, graph, project)
        return replace(run, context=artifacts.run_context())
    thread_id = user_input.thread_id or str(uuid4())
    paths = await artifacts.workspace_paths(records, thread_id)
    attachments = MessageAttachments([artifact_ref(record) for record in records], paths)
    run = await build_run_input(
        user_input.model_copy(update={"thread_id": thread_id}),
        user_id,
        agent,
        graph,
        project,
        attachments,
    )
    await artifacts.link(records, run.thread_id)
    await artifacts.copy_to_workspace(records, paths, run.thread_id)
    return replace(run, context=artifacts.run_context())


def parse_agent_config(agent: BaseAgent, raw_config: dict[str, JsonValue]) -> BaseModel:
    """Validasi `agent_config` dengan error berformat sama seperti validasi body FastAPI (FR-27).

    Args:
        agent: Agent tujuan.
        raw_config: Isi `agent_config` dari request.

    Returns:
        Config yang sudah tervalidasi.

    Raises:
        RequestValidationError: Berisi error per field dengan `loc` diawali
            `("body", "agent_config")`.
    """
    try:
        return agent.parse_config(raw_config)
    except ValidationError as error:
        field_errors = []
        for field_error in error.errors(include_url=False):
            field_errors.append(
                {**field_error, "loc": (*AGENT_CONFIG_LOCATION, *field_error["loc"])}
            )
        raise RequestValidationError(field_errors) from error


def _graph_input_for(
    snapshot: StateSnapshot, message: str, attachments: MessageAttachments | None
) -> GraphInput:
    """Pilih `Command(resume=...)` jika thread sedang interrupt (FR-12), selain itu message baru.

    Lampiran disimpan di `additional_kwargs` message human: referensinya dibaca converter menjadi
    `ChatMessage.artifacts`, dan path workspace-nya dibaca harness untuk model.

    Raises:
        RequestValidationError: Jika ada lampiran untuk jawaban interrupt (422).
    """
    references = [] if attachments is None else list(attachments.references)
    if snapshot.interrupts:
        if references:
            raise RequestValidationError(
                [
                    {
                        "type": "value_error",
                        "loc": ARTIFACT_IDS_LOCATION,
                        "msg": ATTACHMENTS_ON_INTERRUPT_MESSAGE,
                        "input": [reference.id for reference in references],
                    }
                ]
            )
        return Command(resume=message)
    if attachments is None or not references:
        return {"messages": [HumanMessage(content=message)]}
    return {
        "messages": [HumanMessage(content=message, additional_kwargs=attachments.message_kwargs())]
    }


if __name__ == "__main__":
    import asyncio

    from langgraph.checkpoint.memory import InMemorySaver

    from agent_service.agents.chatbot import ChatbotAgent
    from agent_service.llm.fake import FakeModel

    async def _demo() -> None:
        agent = ChatbotAgent()
        graph = agent.build(FakeModel(), InMemorySaver())
        run = await build_run_input(UserInput(message="Halo"), "user-1", agent, graph)
        print(run.thread_id, run.user_id, run.graph_input)

    asyncio.run(_demo())
