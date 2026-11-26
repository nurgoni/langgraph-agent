"""Tool `run_python`/`run_shell` lewat graph agent asli dengan `FakeSandbox` (FR-49).

Acceptance F37: file yang ditulis di sandbox muncul di workspace. Eksekusi di Docker asli (tanpa
jaringan, timeout) dites di e2e Compose.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agent_service.agents.base import AgentGraph
from agent_service.agents.tool_calling import ToolCallingAgent
from agent_service.files.workspace import InMemoryWorkspace
from agent_service.harness.context import ContextBuilder
from agent_service.harness.runtime import HarnessContext
from agent_service.harness.workspace import WorkspaceToolkit
from agent_service.llm.fake import FakeModel
from agent_service.memory.artifacts import ArtifactRecord
from agent_service.sandbox.fake import FakeSandbox
from agent_service.sandbox.model import ExecutionRequest, ExecutionResult, SandboxError

TIMEOUT = 7


@dataclass
class NoPublisher:
    """`ArtifactPublisher` yang tidak pernah dipanggil tool eksekusi."""

    calls: list[str] = field(default_factory=list)

    async def publish(
        self, owner_id: str, thread_id: str, filename: str, content: bytes
    ) -> ArtifactRecord:
        self.calls.append(filename)
        return ArtifactRecord("a", owner_id, thread_id, filename, "x", 0, "a", datetime.now(UTC))


def chart_result(request: ExecutionRequest) -> ExecutionResult:
    return ExecutionResult(
        exit_code=0,
        stdout="total=450\n",
        files={"chart.png": b"\x89PNG", "../escape.txt": b"x"},
    )


def build_graph(calls: Sequence[dict[str, Any]], timeout: int | None = TIMEOUT) -> AgentGraph:
    model = FakeModel(responses=[AIMessage(content="", tool_calls=list(calls)), "done"])
    files = WorkspaceToolkit(output_max_tokens=1000, execution_timeout_seconds=timeout)
    agent = ToolCallingAgent("exec", "Exec", [], ContextBuilder(), files=files)
    return agent.build(model, InMemorySaver())


def config(approval: str | None = None) -> RunnableConfig:
    configurable: dict[str, Any] = {"thread_id": "t1", "user_id": "u1"}
    if approval is not None:
        configurable["project_tool_approval"] = approval
    return RunnableConfig(configurable=configurable)


def tool_messages(result: dict[str, Any]) -> list[ToolMessage]:
    return [message for message in result["messages"] if isinstance(message, ToolMessage)]


def run_call(code: str = "print(450)") -> dict[str, Any]:
    return {"name": "run_python", "args": {"code": code}, "id": "r1"}


async def test_workspace_goes_in_and_new_files_come_back() -> None:
    workspace = InMemoryWorkspace(max_file_bytes=1000)
    await workspace.write("t1", "uploads/sales.csv", b"region,total\nnorth,200\n")
    sandbox = FakeSandbox(chart_result)
    context = HarnessContext(workspace, NoPublisher(), sandbox)

    result = await build_graph([run_call()]).ainvoke(
        {"messages": [HumanMessage("chart it")]}, config(), context=context
    )

    [request] = sandbox.requests
    assert (request.language, request.code, request.timeout_seconds) == ("python", "print(450)", 7)
    assert request.files == {"uploads/sales.csv": b"region,total\nnorth,200\n"}
    assert await workspace.read("t1", "chart.png") == b"\x89PNG"
    [message] = tool_messages(result)
    assert message.content == (
        "Exit code: 0\nstdout:\ntotal=450\n\nFiles saved to the workspace: chart.png\n"
        "Files not saved (invalid path or too large): ../escape.txt"
    )


async def test_shell_commands_and_timeouts_are_reported() -> None:
    sandbox = FakeSandbox(lambda request: ExecutionResult(exit_code=None, timed_out=True))
    context = HarnessContext(InMemoryWorkspace(max_file_bytes=10), NoPublisher(), sandbox)
    shell = {"name": "run_shell", "args": {"command": "yes > /dev/null"}, "id": "s1"}

    result = await build_graph([shell]).ainvoke(
        {"messages": [HumanMessage("loop")]}, config(), context=context
    )

    assert sandbox.requests[0].language == "shell"
    assert str(tool_messages(result)[0].content).startswith("Timed out")


async def test_project_approval_asks_before_running_and_runs_after_yes() -> None:
    sandbox = FakeSandbox(chart_result)
    context = HarnessContext(InMemoryWorkspace(max_file_bytes=1000), NoPublisher(), sandbox)
    graph = build_graph([run_call("print('hi')")])

    asked = await graph.ainvoke(
        {"messages": [HumanMessage("run")]}, config("always"), context=context
    )
    assert sandbox.requests == []
    assert "print('hi')" in asked["__interrupt__"][0].value

    result = await graph.ainvoke(Command(resume="yes, run it"), config("always"), context=context)

    assert len(sandbox.requests) == 1
    assert str(tool_messages(result)[0].content).startswith("Exit code: 0")


async def test_declined_approval_does_not_run_the_code() -> None:
    sandbox = FakeSandbox(chart_result)
    context = HarnessContext(InMemoryWorkspace(max_file_bytes=1000), NoPublisher(), sandbox)
    graph = build_graph([run_call()])

    await graph.ainvoke({"messages": [HumanMessage("run")]}, config("always"), context=context)
    result = await graph.ainvoke(Command(resume="no"), config("always"), context=context)

    assert sandbox.requests == []
    assert "did not approve" in str(tool_messages(result)[0].content)


async def test_sandbox_failures_and_missing_sandbox_are_tool_errors() -> None:
    def fail(request: ExecutionRequest) -> ExecutionResult:
        raise SandboxError("Cannot reach the sandbox runner")

    workspace = InMemoryWorkspace(max_file_bytes=10)
    failing = HarnessContext(workspace, NoPublisher(), FakeSandbox(fail))
    missing = HarnessContext(workspace, NoPublisher(), None)

    for context, expected in (
        (failing, "Cannot reach the sandbox runner"),
        (missing, "Code execution is not available"),
    ):
        result = await build_graph([run_call()]).ainvoke(
            {"messages": [HumanMessage("run")]}, config(), context=context
        )
        [message] = tool_messages(result)
        assert message.status == "error"
        assert expected in str(message.content)


def test_execution_tools_are_bound_only_when_a_sandbox_is_configured() -> None:
    with_sandbox = WorkspaceToolkit(output_max_tokens=100, execution_timeout_seconds=TIMEOUT)
    without = WorkspaceToolkit(output_max_tokens=100)

    assert {"run_python", "run_shell"} <= {tool.name for tool in with_sandbox.tools}
    assert not {"run_python", "run_shell"} & {tool.name for tool in without.tools}


def failing_result(request: ExecutionRequest) -> ExecutionResult:
    return ExecutionResult(exit_code=1, stderr="ZeroDivisionError: division by zero\n")


async def test_non_zero_exit_and_timeout_are_marked_as_tool_errors() -> None:
    workspace = InMemoryWorkspace(max_file_bytes=10)
    cases = (
        (failing_result, "error", "Exit code: 1"),
        (lambda request: ExecutionResult(exit_code=None, timed_out=True), "error", "Timed out"),
        (chart_result, "success", "Exit code: 0"),
    )
    for handler, status, prefix in cases:
        context = HarnessContext(workspace, NoPublisher(), FakeSandbox(handler))
        result = await build_graph([run_call()]).ainvoke(
            {"messages": [HumanMessage("run")]}, config(), context=context
        )
        [message] = tool_messages(result)
        assert (message.status, message.name) == (status, "run_python")
        assert str(message.content).startswith(prefix)


async def test_run_python_with_non_zero_exit_counts_toward_the_retry_limit() -> None:
    """Acceptance F47: `run_python` dengan exit code bukan nol ikut dihitung."""
    sandbox = FakeSandbox(failing_result)
    context = HarnessContext(InMemoryWorkspace(max_file_bytes=10), NoPublisher(), sandbox)
    calls = [AIMessage(content="", tool_calls=[run_call() | {"id": f"r{i}"}]) for i in range(4)]
    model = FakeModel(responses=[*calls, "The script keeps failing."])
    files = WorkspaceToolkit(output_max_tokens=1000, execution_timeout_seconds=TIMEOUT)
    agent = ToolCallingAgent("exec", "Exec", [], ContextBuilder(), files=files)

    result = await agent.build(model, InMemorySaver()).ainvoke(
        {"messages": [HumanMessage("run")]}, config(), context=context
    )

    assert len(sandbox.requests) == 3
    assert "failed 3 times in a row" in str(tool_messages(result)[-1].content)
    assert result["messages"][-1].content == "The script keeps failing."
