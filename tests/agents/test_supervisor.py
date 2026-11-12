from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import PrivateAttr

from agent_service.agents.base import AgentGraph
from agent_service.agents.catalog import create_default_agents
from agent_service.agents.supervisor import (
    SUPERVISOR_AGENT_ID,
    UNKNOWN_EXPERT_TEMPLATE,
    create_supervisor_agent,
    delegation_tool,
    subagent_name,
)
from agent_service.agents.tool_calling import STEP_LIMIT_MESSAGE
from agent_service.llm.fake import FakeModel


class RecordingModel(FakeModel):
    """FakeModel yang merekam message yang diterima di setiap panggilan."""

    _seen: list[list[BaseMessage]] = PrivateAttr(default_factory=list)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> ChatResult:
        self._seen.append(list(messages))
        return super()._generate(messages, stop, run_manager, **kwargs)

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> Iterator[ChatGenerationChunk]:
        self._seen.append(list(messages))
        yield from super()._stream(messages, stop, run_manager, **kwargs)

    @property
    def seen(self) -> list[list[BaseMessage]]:
        return self._seen


class FakeSearch:
    def text(self, query: str, max_results: int) -> Sequence[Mapping[str, Any]]:
        return [{"title": "Python", "href": "https://python.org", "body": "First released 1991"}]


def tool_call(name: str, args: dict[str, str], call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def build(model: FakeModel) -> AgentGraph:
    return create_supervisor_agent(FakeSearch()).build(model, InMemorySaver())


def config(thread_id: str = "t1", recursion_limit: int | None = None) -> RunnableConfig:
    result = RunnableConfig(configurable={"thread_id": thread_id})
    if recursion_limit is not None:
        result["recursion_limit"] = recursion_limit
    return result


DELEGATE_TO_MATH = tool_call("ask_math_expert", {"task": "Compute 12 * 7"}, "s1")
MATH_USES_CALCULATOR = tool_call("calculator", {"expression": "12 * 7"}, "m1")


async def test_delegates_to_expert_and_keeps_its_messages_marked() -> None:
    model = RecordingModel(
        responses=[DELEGATE_TO_MATH, MATH_USES_CALCULATOR, "12 * 7 = 84", "Jawabannya 84."]
    )

    result = await build(model).ainvoke({"messages": [HumanMessage("12 * 7?")]}, config())

    rows = [(type(m).__name__, subagent_name(m), str(m.content)) for m in result["messages"]]
    assert rows == [
        ("HumanMessage", None, "12 * 7?"),
        ("AIMessage", None, ""),
        ("AIMessage", "math_expert", ""),
        ("ToolMessage", "math_expert", "84"),
        ("AIMessage", "math_expert", "12 * 7 = 84"),
        ("ToolMessage", None, "12 * 7 = 84"),
        ("AIMessage", None, "Jawabannya 84."),
    ]


async def test_expert_gets_only_the_task_and_supervisor_never_sees_expert_internals() -> None:
    model = RecordingModel(
        responses=[DELEGATE_TO_MATH, MATH_USES_CALCULATOR, "12 * 7 = 84", "Jawabannya 84."]
    )

    await build(model).ainvoke({"messages": [HumanMessage("12 * 7?")]}, config())

    expert_first_call = model.seen[1]
    assert [m.content for m in expert_first_call[1:]] == ["Compute 12 * 7"]
    supervisor_final_call = model.seen[-1]
    assert all(subagent_name(m) is None for m in supervisor_final_call)
    assert isinstance(supervisor_final_call[-1], ToolMessage)
    assert supervisor_final_call[-1].content == "12 * 7 = 84"


async def test_research_expert_uses_web_search() -> None:
    model = FakeModel(
        responses=[
            tool_call("ask_research_expert", {"task": "When was Python first released?"}, "s1"),
            tool_call("web_search", {"query": "Python first release"}, "r1"),
            "Python dirilis 1991 ([python.org](https://python.org)).",
            "Python pertama kali dirilis tahun 1991.",
        ]
    )

    result = await build(model).ainvoke(
        {"messages": [HumanMessage("Kapan Python rilis?")]}, config()
    )

    search_result = next(
        m for m in result["messages"] if isinstance(m, ToolMessage) and subagent_name(m)
    )
    assert "https://python.org" in str(search_result.content)
    assert result["messages"][-1].content == "Python pertama kali dirilis tahun 1991."


async def test_answers_directly_without_delegating() -> None:
    result = await build(FakeModel(responses=["Halo!"])).ainvoke(
        {"messages": [HumanMessage("Hai")]}, config()
    )

    assert [m.content for m in result["messages"]] == ["Hai", "Halo!"]


async def test_unknown_expert_tool_is_reported_to_supervisor() -> None:
    model = FakeModel(responses=[tool_call("ask_nobody", {"task": "x"}, "s1"), "Maaf."])

    result = await build(model).ainvoke({"messages": [HumanMessage("x")]}, config())

    error = result["messages"][2]
    assert isinstance(error, ToolMessage)
    assert error.status == "error"
    assert error.content == UNKNOWN_EXPERT_TEMPLATE.format(name="ask_nobody")
    assert result["messages"][-1].content == "Maaf."


async def test_expert_runs_start_fresh_in_the_same_thread() -> None:
    model = RecordingModel(
        responses=[
            tool_call("ask_math_expert", {"task": "1 + 1"}, "a"),
            "2",
            "Dua.",
            tool_call("ask_math_expert", {"task": "2 + 2"}, "b"),
            "4",
            "Empat.",
        ]
    )
    graph = build(model)

    await graph.ainvoke({"messages": [HumanMessage("1 + 1?")]}, config())
    await graph.ainvoke({"messages": [HumanMessage("2 + 2?")]}, config())

    second_expert_call = model.seen[4]
    assert [m.content for m in second_expert_call[1:]] == ["2 + 2"]


async def test_step_limit_stops_endless_delegation() -> None:
    model = FakeModel(responses=[tool_call("ask_math_expert", {"task": "loop"}, "s1"), "ok"])

    result = await build(model).ainvoke(
        {"messages": [HumanMessage("x")]}, config(recursion_limit=6)
    )

    assert result["messages"][-1].content == STEP_LIMIT_MESSAGE


def test_delegation_tool_schema_has_single_task_argument() -> None:
    expert = create_supervisor_agent(FakeSearch()).experts[0]

    schema = delegation_tool(expert)["function"]

    assert isinstance(schema, dict)
    assert schema["name"] == "ask_math_expert"
    assert schema["parameters"]["required"] == ["task"]


def test_registered_in_default_catalog() -> None:
    assert SUPERVISOR_AGENT_ID in [agent.agent_id for agent in create_default_agents()]
