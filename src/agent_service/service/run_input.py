"""Penyusunan input dan config untuk satu run agent dari request `UserInput`."""

from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID, uuid4

from fastapi.exceptions import RequestValidationError
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.utils.uuid import uuid7
from langgraph.types import Command, StateSnapshot
from pydantic import BaseModel, JsonValue, ValidationError

from agent_service.agents.base import AgentGraph, BaseAgent
from agent_service.schema.requests import UserInput
from agent_service.service.thread_access import ensure_thread_owner, is_new_thread, run_metadata

AGENT_CONFIG_LOCATION: Final = ("body", "agent_config")

# Any: bentuk input bergantung pada state agent. Command dipakai untuk melanjutkan interrupt.
type GraphInput = dict[str, Any] | Command


@dataclass(frozen=True)
class RunInput:
    """Semua yang dibutuhkan untuk menjalankan graph satu kali."""

    graph_input: GraphInput
    config: RunnableConfig
    run_id: UUID
    thread_id: str
    user_id: str


async def build_run_input(user_input: UserInput, agent: BaseAgent, graph: AgentGraph) -> RunInput:
    """Siapkan input graph untuk request, termasuk ID baru dan resume interrupt.

    Function, bukan class: tidak menyimpan state, dan setiap langkah sudah dipecah ke helper.

    Args:
        user_input: Body request `/invoke` atau `/stream`.
        agent: Agent tujuan, untuk validasi `agent_config`.
        graph: Graph agent untuk model yang dipilih.

    Returns:
        Input dan config run. `thread_id`/`user_id` yang kosong diisi UUID baru (FR-13).

    Raises:
        RequestValidationError: Jika `agent_config` tidak lolos `config_schema` agent (422).
        ThreadNotFoundError: Jika thread sudah ada tapi milik user atau agent lain (404).
    """
    agent_config = parse_agent_config(agent, user_input.agent_config)
    thread_id = user_input.thread_id or str(uuid4())
    user_id = user_input.user_id or str(uuid4())
    run_id = uuid7()
    configurable: dict[str, Any] = {"thread_id": thread_id, "user_id": user_id}
    configurable.update(agent_config.model_dump(mode="json"))
    config = RunnableConfig(
        configurable=configurable,
        metadata=run_metadata(user_id, agent.agent_id),
        run_id=run_id,
    )
    snapshot = await graph.aget_state(config)
    if not is_new_thread(snapshot):
        ensure_thread_owner(snapshot, thread_id, user_id, agent.agent_id)
    return RunInput(
        graph_input=_graph_input_for(snapshot, user_input.message),
        config=config,
        run_id=run_id,
        thread_id=thread_id,
        user_id=user_id,
    )


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


def _graph_input_for(snapshot: StateSnapshot, message: str) -> GraphInput:
    """Pilih `Command(resume=...)` jika thread sedang interrupt (FR-12), selain itu message baru."""
    if snapshot.interrupts:
        return Command(resume=message)
    return {"messages": [HumanMessage(content=message)]}


if __name__ == "__main__":
    import asyncio

    from langgraph.checkpoint.memory import InMemorySaver

    from agent_service.agents.chatbot import ChatbotAgent
    from agent_service.llm.fake import FakeModel

    async def _demo() -> None:
        agent = ChatbotAgent()
        graph = agent.build(FakeModel(), InMemorySaver())
        run = await build_run_input(UserInput(message="Halo"), agent, graph)
        print(run.thread_id, run.user_id, run.graph_input)

    asyncio.run(_demo())
