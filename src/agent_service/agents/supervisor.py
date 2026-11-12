"""Supervisor multi-agent: mendelegasikan tugas ke expert (sub-agent) lalu merangkum jawaban.

Supervisor adalah LLM dengan satu tool delegasi per expert (`ask_<nama>`). Node `delegate`
menjalankan graph expert dengan model yang sama dari request (FR-4), lalu:

- menandai setiap message buatan expert dengan `additional_kwargs[SUBAGENT_KWARG]`, supaya riwayat
  bisa dirender bertingkat (FR-23) tanpa menebak dari nama node atau tool;
- menjalankan expert dengan tag `SUBAGENT_TAG`, supaya token expert tidak dialirkan ke chat utama;
- mengembalikan jawaban akhir expert ke supervisor sebagai `ToolMessage`.

Supervisor hanya melihat message tanpa tanda sub-agent, jadi urutan tool call dan hasilnya tetap
valid untuk API OpenAI-compatible.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.tool import ToolCall
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.managed import RemainingSteps

from agent_service.agents.base import AgentGraph, BaseAgent, Checkpointer
from agent_service.agents.tool_calling import (
    MIN_REMAINING_STEPS,
    STEP_LIMIT_MESSAGE,
    ToolCallingAgent,
)
from agent_service.agents.tools.calculator import calculator
from agent_service.agents.tools.web_search import SearchBackend, create_web_search_tool

SUPERVISOR_AGENT_ID: Final = "supervisor"
SUPERVISOR_DESCRIPTION: Final = (
    "A supervisor that delegates to a math expert and a research expert, then combines answers."
)
SUPERVISOR_NODE: Final = "supervisor"
DELEGATE_NODE: Final = "delegate"
# Tag pada run expert. StreamService tidak mengalirkan token/reasoning dari run bertag ini.
SUBAGENT_TAG: Final = "subagent"
# Kunci `additional_kwargs` berisi nama expert pada setiap message yang dibuat expert.
SUBAGENT_KWARG: Final = "subagent"
DELEGATE_TOOL_PREFIX: Final = "ask_"
TASK_ARG: Final = "task"
UNKNOWN_EXPERT_TEMPLATE: Final = "There is no expert behind the tool {name!r}."
EMPTY_ANSWER_TEXT: Final = "The expert returned no answer."
ERROR_STATUS: Final = "error"

SUPERVISOR_PROMPT: Final = """\
You coordinate a team of experts. Delegate work with the ask_* tools: give each expert one clear,
self-contained task that includes every detail it needs, because experts cannot see this
conversation. Do not search the web or do arithmetic yourself. When you have what you need,
combine the experts' answers into one final reply in the same language as the user."""

MATH_EXPERT_PROMPT: Final = """\
You are a math expert. Solve the task with the calculator tool, one expression at a time, and
reply with the result and a short explanation."""

RESEARCH_EXPERT_PROMPT: Final = """\
You are a research expert with web search. Today's date is {current_date}. Find the facts the
task asks for and cite one or two sources as markdown links returned by web_search. Do not do
arithmetic."""


@dataclass(frozen=True)
class Expert:
    """Sub-agent yang bisa dipanggil supervisor lewat tool `ask_<name>`."""

    name: str
    description: str
    agent: ToolCallingAgent

    @property
    def tool_name(self) -> str:
        """Nama tool delegasi untuk expert ini.

        >>> Expert("math_expert", "Math", ToolCallingAgent("m", "M", [], "")).tool_name
        'ask_math_expert'
        """
        return DELEGATE_TOOL_PREFIX + self.name


class SupervisorState(MessagesState):
    """Riwayat message, termasuk message expert yang ditandai, dan sisa langkah."""

    remaining_steps: RemainingSteps


def delegation_tool(expert: Expert) -> dict[str, object]:
    """Schema tool OpenAI-compatible untuk mendelegasikan satu tugas ke `expert`.

    Ditulis sebagai schema, bukan `@tool`, karena tool ini tidak dijalankan `ToolNode`. Node
    `delegate` yang menjalankan expert-nya.
    """
    return {
        "type": "function",
        "function": {
            "name": expert.tool_name,
            "description": f"Delegate a task to the {expert.name}. {expert.description}",
            "parameters": {
                "type": "object",
                "properties": {
                    TASK_ARG: {
                        "type": "string",
                        "description": "A complete, self-contained task for the expert.",
                    }
                },
                "required": [TASK_ARG],
            },
        },
    }


def subagent_name(message: BaseMessage) -> str | None:
    """Nama expert yang membuat `message`, atau `None` untuk message supervisor/user.

    >>> subagent_name(AIMessage(content="84", additional_kwargs={"subagent": "math_expert"}))
    'math_expert'
    >>> subagent_name(AIMessage(content="Halo")) is None
    True
    """
    value = message.additional_kwargs.get(SUBAGENT_KWARG)
    return value if isinstance(value, str) else None


def mark_subagent_message(message: BaseMessage, expert_name: str) -> BaseMessage:
    """Salinan `message` yang ditandai sebagai buatan `expert_name`."""
    additional_kwargs = {**message.additional_kwargs, SUBAGENT_KWARG: expert_name}
    return message.model_copy(update={"additional_kwargs": additional_kwargs})


def route_supervisor(state: SupervisorState) -> str:
    """Delegasikan jika supervisor memanggil tool, selain itu selesai."""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return DELEGATE_NODE
    return END


class SupervisorAgent(BaseAgent):
    """Agent multi-agent: supervisor mendelegasikan ke daftar `Expert`."""

    def __init__(
        self,
        agent_id: str,
        description: str,
        experts: Sequence[Expert],
        system_prompt: str = SUPERVISOR_PROMPT,
    ) -> None:
        """Inisialisasi supervisor.

        Args:
            agent_id: ID agent di registry.
            description: Deskripsi untuk `/info`.
            experts: Sub-agent yang bisa dipanggil. Nama harus unik.
            system_prompt: Instruksi untuk supervisor.
        """
        super().__init__(agent_id=agent_id, description=description)
        self._experts = list(experts)
        self._system_prompt = system_prompt

    @property
    def experts(self) -> list[Expert]:
        """Expert yang bisa dipanggil supervisor, urut sesuai pendaftaran."""
        return list(self._experts)

    def build(self, model: BaseChatModel, checkpointer: Checkpointer) -> AgentGraph:
        """Compile graph `supervisor ⇄ delegate`. Supervisor dan semua expert memakai `model`.

        Args:
            model: Chat model dari request, dipakai juga oleh setiap expert (FR-4).
            checkpointer: Saver tempat riwayat thread, termasuk message expert, disimpan.

        Returns:
            Graph yang sudah di-compile.
        """
        supervisor_model = model.bind_tools([delegation_tool(e) for e in self._experts])
        expert_graphs = {
            expert.tool_name: (expert, expert.agent.build_stateless(model))
            for expert in self._experts
        }

        # Closure, bukan method: satu instance agent membangun graph untuk beberapa model.
        async def supervise(state: SupervisorState) -> dict[str, list[AIMessage]]:
            visible = [m for m in state["messages"] if subagent_name(m) is None]
            prompt = SystemMessage(content=self._system_prompt)
            response = await supervisor_model.ainvoke([prompt, *visible])
            if response.tool_calls and state["remaining_steps"] < MIN_REMAINING_STEPS:
                return {"messages": [AIMessage(id=response.id, content=STEP_LIMIT_MESSAGE)]}
            return {"messages": [response]}

        async def delegate(state: SupervisorState) -> dict[str, list[BaseMessage]]:
            last = state["messages"][-1]
            if not isinstance(last, AIMessage):
                return {"messages": []}
            produced: list[BaseMessage] = []
            for call in last.tool_calls:
                produced.extend(await run_expert(call, expert_graphs))
            return {"messages": produced}

        # pyrefly tidak mengenali TypedDict sebagai TypedDictLike milik LangGraph.
        builder = StateGraph(SupervisorState)  # pyrefly: ignore[bad-specialization]
        builder.add_node(SUPERVISOR_NODE, supervise)
        builder.add_node(DELEGATE_NODE, delegate)
        builder.add_edge(START, SUPERVISOR_NODE)
        builder.add_conditional_edges(SUPERVISOR_NODE, route_supervisor)
        builder.add_edge(DELEGATE_NODE, SUPERVISOR_NODE)
        return builder.compile(checkpointer=checkpointer)


async def run_expert(
    call: ToolCall, expert_graphs: Mapping[str, tuple[Expert, AgentGraph]]
) -> list[BaseMessage]:
    """Jalankan expert untuk satu tool call delegasi.

    Args:
        call: Tool call `ask_<expert>` dari supervisor.
        expert_graphs: Expert dan graph stateless-nya, per nama tool.

    Returns:
        Message expert yang sudah ditandai, diikuti `ToolMessage` berisi jawaban akhir expert
        untuk supervisor. Tool yang tidak dikenal menghasilkan `ToolMessage` berstatus error.
    """
    call_id = call["id"] or ""
    entry = expert_graphs.get(call["name"])
    if entry is None:
        error = UNKNOWN_EXPERT_TEMPLATE.format(name=call["name"])
        return [ToolMessage(content=error, tool_call_id=call_id, status=ERROR_STATUS)]
    expert, graph = entry
    task = HumanMessage(content=str(call["args"].get(TASK_ARG, "")))
    tagged_graph = graph.with_config(tags=[SUBAGENT_TAG], run_name=expert.name)
    result = await tagged_graph.ainvoke({"messages": [task]})
    expert_messages = [mark_subagent_message(m, expert.name) for m in result["messages"][1:]]
    final = expert_messages[-1] if expert_messages else None
    answer = str(final.content) if isinstance(final, AIMessage) and final.content else ""
    summary = ToolMessage(
        content=answer or EMPTY_ANSWER_TEXT, tool_call_id=call_id, name=call["name"]
    )
    return [*expert_messages, summary]


def create_supervisor_agent(search_backend: SearchBackend | None = None) -> SupervisorAgent:
    """Buat supervisor dengan `math_expert` (kalkulator) dan `research_expert` (web search).

    Function, bukan class: factory konfigurasi tanpa state sendiri.

    Args:
        search_backend: Mesin pencari untuk research expert. Default: DuckDuckGo.

    Returns:
        Agent `supervisor` yang siap didaftarkan.

    >>> [expert.tool_name for expert in create_supervisor_agent().experts]
    ['ask_math_expert', 'ask_research_expert']
    """
    math_expert = Expert(
        name="math_expert",
        description="Solves arithmetic and math problems with a calculator.",
        agent=ToolCallingAgent("math_expert", "Math expert", [calculator], MATH_EXPERT_PROMPT),
    )
    research_expert = Expert(
        name="research_expert",
        description="Looks up current facts on the web and cites sources. Does no arithmetic.",
        agent=ToolCallingAgent(
            "research_expert",
            "Research expert",
            [create_web_search_tool(search_backend)],
            RESEARCH_EXPERT_PROMPT,
        ),
    )
    return SupervisorAgent(
        agent_id=SUPERVISOR_AGENT_ID,
        description=SUPERVISOR_DESCRIPTION,
        experts=[math_expert, research_expert],
    )
