"""Tool file workspace dan offloader lewat graph agent asli (FR-47, FR-48).

Acceptance F36: path traversal ditolak, workspace thread lain tidak terbaca, dan output tool besar
diganti cuplikan + path.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatResult
from langchain_core.tools import BaseTool, tool
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import Field

from agent_service.agents.tool_calling import ToolCallingAgent
from agent_service.files.workspace import InMemoryWorkspace
from agent_service.harness.context import ContextBuilder
from agent_service.harness.runtime import HarnessContext
from agent_service.harness.workspace import WorkspaceToolkit
from agent_service.llm.fake import FakeModel
from agent_service.memory.artifacts import ArtifactRecord
from agent_service.service.converters import langchain_to_chat_message

MAX_TOKENS = 100
MAX_CHARS = MAX_TOKENS * 4
BIG_OUTPUT = "row," * 500


@dataclass
class RecordingPublisher:
    """`ArtifactPublisher` palsu yang mencatat file yang dibagikan."""

    published: list[tuple[str, str, str, bytes]] = field(default_factory=list)

    async def publish(
        self, owner_id: str, thread_id: str, filename: str, content: bytes
    ) -> ArtifactRecord:
        self.published.append((owner_id, thread_id, filename, content))
        return ArtifactRecord(
            artifact_id="a1",
            owner_id=owner_id,
            thread_id=thread_id,
            name=filename,
            mime_type="text/markdown",
            size_bytes=len(content),
            storage_key="a1",
            created_at=datetime.now(UTC),
        )


@tool
def big_report() -> str:
    """Return a very large report."""
    return BIG_OUTPUT


def call(name: str, call_id: str = "c1", **args: Any) -> dict[str, Any]:  # Any: argumen tool
    return {"name": name, "args": args, "id": call_id}


async def run_calls(
    calls: Sequence[dict[str, Any]],  # Any: tool call
    workspace: InMemoryWorkspace,
    thread_id: str = "t1",
    publisher: RecordingPublisher | None = None,
    extra_tools: Sequence[BaseTool] = (),
    with_context: bool = True,
) -> list[ToolMessage]:
    model = FakeModel(responses=[AIMessage(content="", tool_calls=list(calls)), "done"])
    files = WorkspaceToolkit(output_max_tokens=MAX_TOKENS)
    agent = ToolCallingAgent("files", "Files", list(extra_tools), ContextBuilder(), files=files)
    graph = agent.build(model, InMemorySaver())
    context = HarnessContext(workspace, publisher or RecordingPublisher()) if with_context else None
    config = {"configurable": {"thread_id": thread_id, "user_id": "u1"}}
    result = await graph.ainvoke({"messages": [HumanMessage("go")]}, config, context=context)
    return [message for message in result["messages"] if isinstance(message, ToolMessage)]


def contents(messages: Sequence[ToolMessage]) -> list[str]:
    return [str(message.content) for message in messages]


async def test_written_file_is_read_back_with_line_numbers() -> None:
    workspace = InMemoryWorkspace(max_file_bytes=1000)

    messages = await run_calls(
        [
            call("write_file", "c1", path="notes/todo.md", content="buy milk\ncall Rani"),
            call("read_file", "c2", path="./notes/todo.md"),
        ],
        workspace,
    )

    assert contents(messages) == [
        "Wrote 18 bytes to notes/todo.md.",
        "     1\tbuy milk\n     2\tcall Rani",
    ]


async def test_path_traversal_is_rejected() -> None:
    workspace = InMemoryWorkspace(max_file_bytes=1000)

    [message] = await run_calls([call("write_file", path="../escape.txt", content="x")], workspace)

    assert message.status == "error"
    assert "must stay inside the workspace" in str(message.content)
    assert await workspace.list_files("t1") == []


async def test_workspace_of_another_thread_is_not_readable() -> None:
    workspace = InMemoryWorkspace(max_file_bytes=1000)
    await workspace.write("t1", "secret.txt", b"mine")

    read, listed = await run_calls(
        [call("read_file", "c1", path="secret.txt"), call("list_files", "c2")],
        workspace,
        thread_id="t2",
    )

    assert read.status == "error"
    assert "does not exist in the workspace" in str(read.content)
    assert listed.content == "No files in the workspace."


async def test_edit_requires_exactly_one_match() -> None:
    workspace = InMemoryWorkspace(max_file_bytes=1000)
    await workspace.write("t1", "a.txt", b"x = 1\ny = 1\n")

    missing, ambiguous, edited = await run_calls(
        [
            call("edit_file", "c1", path="a.txt", old_text="z = 1", new_text="z = 2"),
            call("edit_file", "c2", path="a.txt", old_text="= 1", new_text="= 2"),
            call("edit_file", "c3", path="a.txt", old_text="y = 1", new_text="y = 2"),
        ],
        workspace,
    )

    assert "was not found" in str(missing.content)
    assert "appears 2 times" in str(ambiguous.content)
    assert edited.content == "Edited a.txt."
    assert await workspace.read("t1", "a.txt") == b"x = 1\ny = 2\n"


async def test_grep_matches_text_literally() -> None:
    workspace = InMemoryWorkspace(max_file_bytes=1000)
    await workspace.write("t1", "data/a.txt", b"Total: 10\nabc\n")
    await workspace.write("t1", "data/b.bin", b"\xff\xfeTotal")
    await workspace.write("t1", "other.txt", b"total: 3\n")

    exact, folder, regex_like = await run_calls(
        [
            call("grep", "c1", text="total", ignore_case=True),
            call("grep", "c2", text="Total", folder="data"),
            call("grep", "c3", text="a.c"),
        ],
        workspace,
    )

    assert exact.content == "data/a.txt:1: Total: 10\nother.txt:1: total: 3"
    assert folder.content == "data/a.txt:1: Total: 10"
    assert regex_like.content == "No lines contain 'a.c'."


async def test_binary_files_are_not_read_as_text() -> None:
    workspace = InMemoryWorkspace(max_file_bytes=1000)
    await workspace.write("t1", "chart.png", b"\x89PNG\r\n\x1a\n\xff")

    [message] = await run_calls([call("read_file", path="chart.png")], workspace)

    assert "binary file" in str(message.content)
    assert "share_file" in str(message.content)


async def test_shared_file_becomes_an_artifact_on_the_tool_message() -> None:
    workspace = InMemoryWorkspace(max_file_bytes=1000)
    await workspace.write("t1", "reports/summary.md", b"# Q3")
    publisher = RecordingPublisher()

    [message] = await run_calls(
        [call("share_file", path="reports/summary.md")], workspace, publisher=publisher
    )

    assert publisher.published == [("u1", "t1", "summary.md", b"# Q3")]
    assert message.content == "Shared reports/summary.md with the user as summary.md."
    artifact = langchain_to_chat_message(message).artifacts[0]
    assert (artifact.id, artifact.name, artifact.size) == ("a1", "summary.md", 4)


async def test_tools_explain_when_the_run_has_no_workspace() -> None:
    [message] = await run_calls(
        [call("list_files")], InMemoryWorkspace(max_file_bytes=10), with_context=False
    )

    assert message.status == "error"
    assert "The workspace is not available in this conversation." in str(message.content)


# ---------------- offloading output besar (FR-48)


async def test_large_tool_output_is_replaced_by_a_preview_and_a_path() -> None:
    workspace = InMemoryWorkspace(max_file_bytes=10_000)

    [message] = await run_calls([call("big_report", "call/9")], workspace, extra_tools=[big_report])

    content = str(message.content)
    assert len(content) < MAX_CHARS
    assert content.startswith(BIG_OUTPUT[: MAX_CHARS // 4])
    assert "saved in the workspace at tool-outputs/call_9.txt" in content
    assert await workspace.read("t1", "tool-outputs/call_9.txt") == BIG_OUTPUT.encode()


async def test_large_output_is_truncated_when_there_is_no_workspace() -> None:
    [message] = await run_calls(
        [call("big_report")],
        InMemoryWorkspace(max_file_bytes=10),
        extra_tools=[big_report],
        with_context=False,
    )

    assert "Output truncated" in str(message.content)
    assert len(str(message.content)) < MAX_CHARS


async def test_reading_a_large_file_pages_instead_of_offloading() -> None:
    workspace = InMemoryWorkspace(max_file_bytes=100_000)
    lines = "\n".join(f"line {number}" for number in range(1, 2001))
    await workspace.write("t1", "big.txt", lines.encode())

    [message] = await run_calls([call("read_file", path="big.txt")], workspace)

    content = str(message.content)
    assert content.startswith("     1\tline 1")
    assert "Continue with offset=" in content
    assert [file.path for file in await workspace.list_files("t1")] == ["big.txt"]


class InputRecordingModel(FakeModel):
    """FakeModel yang mencatat message yang diterima setiap panggilan."""

    received: list[list[BaseMessage]] = Field(default_factory=list)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> ChatResult:
        self.received.append(list(messages))
        return super()._generate(messages, stop, run_manager, **kwargs)


async def test_model_sees_attachment_paths_but_history_stays_unchanged() -> None:
    model = InputRecordingModel(responses=["Read it."])
    files = WorkspaceToolkit(output_max_tokens=MAX_TOKENS)
    graph = ToolCallingAgent("files", "Files", [], ContextBuilder(), files=files).build(
        model, InMemorySaver()
    )
    human = HumanMessage(
        "Summarize this", additional_kwargs={"workspace_files": ["uploads/sales.csv"]}
    )

    result = await graph.ainvoke({"messages": [human]}, {"configurable": {"thread_id": "t1"}})

    sent = model.received[0][-1]
    assert "Summarize this" in str(sent.content)
    assert "- uploads/sales.csv" in str(sent.content)
    assert result["messages"][0].content == "Summarize this"
