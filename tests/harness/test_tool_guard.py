"""`ToolFailureGuard` lewat graph `ToolCallingAgent` asli dengan `FakeModel` (FR-59, F47)."""

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, ToolException, tool
from langgraph.checkpoint.memory import InMemorySaver

from agent_service.agents.base import AgentGraph
from agent_service.agents.tool_calling import ToolCallingAgent
from agent_service.harness.context import ContextBuilder
from agent_service.harness.tool_guard import ToolFailureGuard, consecutive_failures
from agent_service.harness.workspace import WorkspaceToolkit
from agent_service.llm.fake import FakeModel

FINAL_ANSWER = "The tool keeps failing: service down."


class FlakyTool:
    """Tool `flaky` yang gagal jika argumennya `"fail"`, dan mencatat setiap eksekusi."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def as_tool(self) -> BaseTool:
        @tool("flaky")
        def flaky(mode: str) -> str:
            """Fails when mode is "fail"."""
            self.calls.append(mode)
            if mode == "fail":
                raise ToolException("service down")
            return "ok"

        return flaky


def flaky_call(mode: str, call_id: str) -> AIMessage:
    return AIMessage(
        content="", tool_calls=[{"name": "flaky", "args": {"mode": mode}, "id": call_id}]
    )


def build(
    responses: list[AIMessage | str],
    tools: list[BaseTool],
    guard: ToolFailureGuard | None = None,
    files: WorkspaceToolkit | None = None,
) -> AgentGraph:
    agent = ToolCallingAgent(
        "guarded", "Guarded", tools, ContextBuilder(), files=files, tool_guard=guard
    )
    return agent.build(FakeModel(responses=responses), InMemorySaver())


def config() -> RunnableConfig:
    return RunnableConfig(configurable={"thread_id": "t1", "user_id": "u1"})


def tool_results(messages: list[BaseMessage]) -> list[ToolMessage]:
    return [message for message in messages if isinstance(message, ToolMessage)]


async def test_tool_stops_after_three_consecutive_failures_and_model_answers() -> None:
    """Acceptance F47: berhenti setelah 3 kegagalan beruntun, lalu menjawab tanpa tool itu."""
    flaky = FlakyTool()
    responses: list[AIMessage | str] = [flaky_call("fail", f"c{i}") for i in range(4)]
    graph = build([*responses, FINAL_ANSWER], [flaky.as_tool()])

    result = await graph.ainvoke({"messages": [HumanMessage("go")]}, config())

    assert flaky.calls == ["fail", "fail", "fail"]
    results = tool_results(result["messages"])
    assert [message.status for message in results] == ["error"] * 4
    assert "failed 3 times in a row" in str(results[-1].content)
    assert "Do not call flaky again" in str(results[-1].content)
    assert results[-1].name == "flaky"
    assert result["messages"][-1].content == FINAL_ANSWER


async def test_success_between_failures_resets_the_count() -> None:
    """Acceptance F47: keberhasilan di antara kegagalan me-reset hitungan."""
    flaky = FlakyTool()
    modes = ["fail", "fail", "ok", "fail", "fail"]
    responses: list[AIMessage | str] = [flaky_call(m, f"c{i}") for i, m in enumerate(modes)]
    graph = build([*responses, "done"], [flaky.as_tool()])

    result = await graph.ainvoke({"messages": [HumanMessage("go")]}, config())

    assert flaky.calls == modes
    assert not any("in a row" in str(m.content) for m in tool_results(result["messages"]))


async def test_new_human_turn_starts_a_fresh_count() -> None:
    flaky = FlakyTool()
    first: list[AIMessage | str] = [flaky_call("fail", f"a{i}") for i in range(3)]
    graph = build([*first, "sorry", flaky_call("fail", "b0"), "still down"], [flaky.as_tool()])

    await graph.ainvoke({"messages": [HumanMessage("go")]}, config())
    await graph.ainvoke({"messages": [HumanMessage("try again")]}, config())

    assert flaky.calls == ["fail"] * 4


async def test_limit_is_configurable_and_other_tools_keep_running() -> None:
    flaky = FlakyTool()

    @tool("echo")
    def echo(text: str) -> str:
        """Echo text."""
        return text

    echo_call = AIMessage(
        content="", tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "e1"}]
    )
    responses: list[AIMessage | str] = [
        flaky_call("fail", "c1"),
        flaky_call("fail", "c2"),
        echo_call,
        "done",
    ]
    graph = build(responses, [flaky.as_tool(), echo], ToolFailureGuard(1))

    result = await graph.ainvoke({"messages": [HumanMessage("go")]}, config())

    assert flaky.calls == ["fail"]
    assert tool_results(result["messages"])[-1].content == "hi"


async def test_bug_in_a_tool_is_not_hidden_when_files_wrap_the_tool_node() -> None:
    """Dengan wrapper, `ToolNode` bawaan mengubah semua exception menjadi pesan error."""

    @tool("broken")
    def broken(value: str) -> str:
        """Always fails with a bug."""
        raise RuntimeError("bug")

    call = AIMessage(
        content="", tool_calls=[{"name": "broken", "args": {"value": "x"}, "id": "b1"}]
    )
    graph = build([call, "done"], [broken], files=WorkspaceToolkit(output_max_tokens=1000))

    with pytest.raises(RuntimeError, match="bug"):
        await graph.ainvoke({"messages": [HumanMessage("x")]}, config())


async def test_guard_wraps_the_output_offloader_when_files_are_configured() -> None:
    flaky = FlakyTool()
    responses: list[AIMessage | str] = [flaky_call("fail", f"c{i}") for i in range(4)]
    files = WorkspaceToolkit(output_max_tokens=1000)
    graph = build([*responses, FINAL_ANSWER], [flaky.as_tool()], files=files)

    result = await graph.ainvoke({"messages": [HumanMessage("go")]}, config())

    assert flaky.calls == ["fail"] * 3
    assert "in a row" in str(tool_results(result["messages"])[-1].content)


def test_failures_are_matched_by_tool_call_name_not_message_name() -> None:
    messages: list[BaseMessage] = [
        HumanMessage("go"),
        flaky_call("fail", "c1"),
        ToolMessage("exit 1", tool_call_id="c1", status="error"),
    ]

    assert consecutive_failures(messages, "flaky") == 1
