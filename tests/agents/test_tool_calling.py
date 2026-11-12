from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.tools import BaseTool, ToolException, tool
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import PrivateAttr

from agent_service.agents.base import AgentGraph
from agent_service.agents.tool_calling import STEP_LIMIT_MESSAGE, ToolCallingAgent, local_now
from agent_service.agents.tools.calculator import calculator
from agent_service.llm.fake import FakeModel

FIXED_NOW = datetime(2026, 11, 12, 9, 30, tzinfo=UTC)
PROMPT = "You are a test agent. Today's date is {current_date}."


class RecordingModel(FakeModel):
    """FakeModel yang merekam tools yang di-bind dan message yang diterima di setiap panggilan."""

    _bound_tools: list[str] = PrivateAttr(default_factory=list)
    _seen: list[list[BaseMessage]] = PrivateAttr(default_factory=list)

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],  # Any: API induk
        *,
        tool_choice: str | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> Runnable[LanguageModelInput, AIMessage]:
        self._bound_tools = [getattr(item, "name", str(item)) for item in tools]
        return self

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
    def bound_tools(self) -> list[str]:
        return self._bound_tools

    @property
    def seen(self) -> list[list[BaseMessage]]:
        return self._seen


def calculator_call(expression: str, call_id: str = "c1") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "calculator", "args": {"expression": expression}, "id": call_id}],
    )


def make_agent(tools: Sequence[BaseTool] = (calculator,)) -> ToolCallingAgent:
    return ToolCallingAgent("tester", "Test agent", tools, PROMPT, clock=lambda: FIXED_NOW)


def thread(thread_id: str = "t1", recursion_limit: int | None = None) -> RunnableConfig:
    config = RunnableConfig(configurable={"thread_id": thread_id})
    if recursion_limit is not None:
        config["recursion_limit"] = recursion_limit
    return config


async def run(graph: AgentGraph, question: str, config: RunnableConfig) -> list[BaseMessage]:
    result = await graph.ainvoke({"messages": [HumanMessage(question)]}, config)
    return result["messages"]


async def test_tool_loop_runs_tool_then_answers() -> None:
    model = RecordingModel(responses=[calculator_call("12 * 7"), "12 x 7 = 84"])
    graph = make_agent().build(model, InMemorySaver())

    messages = await run(graph, "Berapa 12 * 7?", thread())

    assert [type(m).__name__ for m in messages] == [
        "HumanMessage",
        "AIMessage",
        "ToolMessage",
        "AIMessage",
    ]
    tool_result = messages[2]
    assert isinstance(tool_result, ToolMessage)
    assert (tool_result.content, tool_result.tool_call_id) == ("84", "c1")
    assert messages[-1].content == "12 x 7 = 84"


async def test_model_sees_dated_system_prompt_and_bound_tools() -> None:
    model = RecordingModel(responses=["Halo"])
    graph = make_agent().build(model, InMemorySaver())

    await run(graph, "Hai", thread())

    first_prompt = model.seen[0][0]
    assert isinstance(first_prompt, SystemMessage)
    assert first_prompt.content == "You are a test agent. Today's date is November 12, 2026."
    assert model.bound_tools == ["calculator"]


async def test_system_prompt_is_not_stored_in_history() -> None:
    graph = make_agent().build(RecordingModel(responses=["Halo"]), InMemorySaver())

    messages = await run(graph, "Hai", thread())

    assert not any(isinstance(m, SystemMessage) for m in messages)


async def test_date_is_computed_at_call_time() -> None:
    moments = iter([datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)])
    model = RecordingModel(responses=["satu", "dua"])
    agent = ToolCallingAgent("t", "T", [calculator], PROMPT, clock=lambda: next(moments))
    graph = agent.build(model, InMemorySaver())

    await run(graph, "a", thread())
    await run(graph, "b", thread())

    dates = [str(seen[0].content).rsplit(" ", 3)[-3:] for seen in model.seen]
    assert dates == [["January", "01,", "2026."], ["January", "02,", "2026."]]


async def test_tool_error_is_returned_to_model_which_can_retry() -> None:
    model = RecordingModel(
        responses=[calculator_call("12 *", "bad"), calculator_call("12 * 7", "good"), "84"]
    )
    graph = make_agent().build(model, InMemorySaver())

    messages = await run(graph, "12 * 7?", thread())

    error_result = messages[2]
    assert isinstance(error_result, ToolMessage)
    assert error_result.status == "error"
    assert "calculator" in str(error_result.content)
    assert messages[-1].content == "84"


async def test_step_limit_stops_endless_tool_calls() -> None:
    model = RecordingModel(responses=[calculator_call("1 + 1")])
    graph = make_agent().build(model, InMemorySaver())

    messages = await run(graph, "Loop", thread(recursion_limit=6))

    assert messages[-1].content == STEP_LIMIT_MESSAGE
    assert not getattr(messages[-1], "tool_calls", None)


async def test_unexpected_tool_bug_is_not_hidden() -> None:
    @tool("broken")
    def broken(value: str) -> str:
        """Always fails with a bug."""
        raise RuntimeError("bug")

    model = RecordingModel(
        responses=[
            AIMessage(
                content="", tool_calls=[{"name": "broken", "args": {"value": "x"}, "id": "b1"}]
            )
        ]
    )
    graph = make_agent([broken]).build(model, InMemorySaver())

    with pytest.raises(RuntimeError, match="bug"):
        await run(graph, "x", thread())


async def test_tool_exception_from_any_tool_is_reported() -> None:
    @tool("flaky")
    def flaky(value: str) -> str:
        """Fails like a network tool."""
        raise ToolException("service down")

    model = RecordingModel(
        responses=[
            AIMessage(
                content="", tool_calls=[{"name": "flaky", "args": {"value": "x"}, "id": "f1"}]
            ),
            "Maaf, layanan sedang tidak tersedia.",
        ]
    )
    graph = make_agent([flaky]).build(model, InMemorySaver())

    messages = await run(graph, "x", thread())

    assert "service down" in str(messages[2].content)
    assert messages[-1].content == "Maaf, layanan sedang tidak tersedia."


def test_local_now_is_timezone_aware() -> None:
    assert local_now().tzinfo is not None


async def test_stateless_graph_starts_fresh_on_every_call() -> None:
    model = RecordingModel(responses=["satu", "dua"])
    graph = make_agent().build_stateless(model)

    first = await graph.ainvoke({"messages": [HumanMessage("a")]}, thread())
    second = await graph.ainvoke({"messages": [HumanMessage("b")]}, thread())

    assert [m.content for m in first["messages"]] == ["a", "satu"]
    assert [m.content for m in second["messages"]] == ["b", "dua"]
    assert graph.checkpointer is False
