"""Tool data (FR-51) lewat graph `ToolCallingAgent` asli, `FakeModel`, dan database demo.

Acceptance F39: tool tidak bisa mengakses data source di luar project, dan tool yang sama bekerja
di kedua dataset demo tanpa perubahan kode.
"""

import io
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import pyarrow.parquet as pq
import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import PrivateAttr

from agent_service.agents.tool_calling import ToolCallingAgent
from agent_service.agents.tools.data import DataAccess, DataToolkit
from agent_service.core.env import EnvReader
from agent_service.datasource.model import DataSourceEntry
from agent_service.datasource.registry import DataSourceRegistry
from agent_service.files.workspace import InMemoryWorkspace
from agent_service.harness.context import ContextBuilder
from agent_service.harness.runtime import HarnessContext
from agent_service.llm.fake import FakeModel
from agent_service.memory.artifacts import ArtifactRecord

MAX_ROWS = 50
WORKSPACE_MAX_BYTES = 5_000_000


class BindingModel(FakeModel):
    """FakeModel yang mencatat tool yang ter-bind pada setiap panggilan model.

    `bind_tools` mengembalikan salinan dengan daftar tool sendiri, dan semua salinan berbagi log
    panggilan, jadi test melihat tool yang benar-benar aktif di setiap giliran.
    """

    _tool_names: list[str] = PrivateAttr(default_factory=list)
    _calls: list[list[str]] = PrivateAttr(default_factory=list)

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],  # Any: API induk
        *,
        tool_choice: str | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> Runnable[LanguageModelInput, AIMessage]:
        bound = self.model_copy()
        bound._tool_names = [tool.name for tool in tools if isinstance(tool, BaseTool)]
        bound._calls = self._calls
        return bound

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> ChatResult:
        self._calls.append(list(self._tool_names))
        return super()._generate(messages, stop, run_manager, **kwargs)

    @property
    def calls(self) -> list[list[str]]:
        return self._calls


class NoPublisher:
    """`ArtifactPublisher` yang tidak dipakai tool data."""

    async def publish(
        self, owner_id: str, thread_id: str, filename: str, content: bytes
    ) -> ArtifactRecord:
        return ArtifactRecord("a", owner_id, thread_id, filename, "x", 0, "a", datetime.now(UTC))


@pytest.fixture
async def registry(demo_database_urls: dict[str, str]) -> AsyncIterator[DataSourceRegistry]:
    urls = {"SHOP_URL": demo_database_urls["shop"], "SENSORS_URL": demo_database_urls["sensors"]}
    env = EnvReader(environ=urls, env_file=None)
    entries = [
        DataSourceEntry(id="shop", description="Store orders", url_env="SHOP_URL"),
        DataSourceEntry(id="sensors", description="Sensor readings", url_env="SENSORS_URL"),
    ]
    opened = DataSourceRegistry(entries, env, timeout_seconds=10)
    await opened.open()
    yield opened
    await opened.close()


@pytest.fixture
def workspace() -> InMemoryWorkspace:
    return InMemoryWorkspace(max_file_bytes=WORKSPACE_MAX_BYTES)


def tool_call(tool_name: str, /, **args: object) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": tool_name, "args": dict(args), "id": "c1"}])


def project_config(*data_source_ids: str) -> RunnableConfig:
    return RunnableConfig(
        configurable={
            "thread_id": "t1",
            "user_id": "u1",
            "project_data_source_ids": list(data_source_ids),
        }
    )


async def run_tool(
    registry: DataSourceRegistry,
    workspace: InMemoryWorkspace,
    call: AIMessage,
    config: RunnableConfig,
    max_rows: int = MAX_ROWS,
) -> ToolMessage:
    data = DataToolkit(DataAccess(registry, max_rows, profile_exact_max_rows=1_000_000))
    agent = ToolCallingAgent("analyst", "Analyst", [], ContextBuilder(), data=data)
    graph = agent.build(FakeModel(responses=[call, "done"]), InMemorySaver())
    context = HarnessContext(workspace, NoPublisher())
    result = await graph.ainvoke({"messages": [HumanMessage("go")]}, config, context=context)
    [message] = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    return message


async def test_data_tools_are_bound_only_in_projects_with_data_sources(
    registry: DataSourceRegistry,
) -> None:
    data = DataToolkit(DataAccess(registry, MAX_ROWS, 1_000_000))
    agent = ToolCallingAgent("analyst", "Analyst", [], ContextBuilder(), data=data)
    model = BindingModel(responses=["a", "b"])
    graph = agent.build(model, InMemorySaver())

    await graph.ainvoke({"messages": [HumanMessage("hi")]}, project_config())
    await graph.ainvoke({"messages": [HumanMessage("hi")]}, project_config("shop"))

    data_tools = [tool.name for tool in data.tools]
    assert data_tools[0] == "list_data_sources" and data_tools[-1] == "run_sql"
    assert model.calls == [[], data_tools]


async def test_list_data_sources_shows_only_project_sources(
    registry: DataSourceRegistry, workspace: InMemoryWorkspace
) -> None:
    message = await run_tool(
        registry, workspace, tool_call("list_data_sources"), project_config("sensors")
    )

    assert message.content == "- sensors: Sensor readings"


@pytest.mark.parametrize(
    "call",
    [
        tool_call("run_sql", sql="SELECT 1", name="x", data_source="shop"),
        tool_call("describe_table", table="orders", data_source="shop"),
        tool_call("profile_table", table="orders", data_source="shop"),
        tool_call("search_schema", keyword="order", data_source="shop"),
    ],
    ids=["run_sql", "describe_table", "profile_table", "search_schema"],
)
async def test_tools_cannot_reach_a_data_source_outside_the_project(
    registry: DataSourceRegistry, workspace: InMemoryWorkspace, call: AIMessage
) -> None:
    """Acceptance F39: data source di luar project ditolak, walaupun terdaftar di registry."""
    message = await run_tool(registry, workspace, call, project_config("sensors"))

    assert message.status == "error"
    assert "'shop' is not available in this project" in str(message.content)


async def test_tools_outside_any_project_have_no_data_source(
    registry: DataSourceRegistry, workspace: InMemoryWorkspace
) -> None:
    call = tool_call("run_sql", sql="SELECT 1", name="x")

    message = await run_tool(registry, workspace, call, project_config())

    assert message.status == "error"
    assert "No data sources are active" in str(message.content)


async def test_several_project_sources_need_an_explicit_choice(
    registry: DataSourceRegistry, workspace: InMemoryWorkspace
) -> None:
    call = tool_call("describe_table", table="orders")

    message = await run_tool(registry, workspace, call, project_config("shop", "sensors"))

    assert "Pass data_source with one of them" in str(message.content)


@pytest.mark.parametrize(
    ("dataset", "table", "group_column", "groups"),
    [("shop", "orders", "channel", 3), ("sensors", "devices", "kind", 3)],
)
async def test_same_tools_work_on_both_demo_datasets(
    registry: DataSourceRegistry,
    workspace: InMemoryWorkspace,
    dataset: str,
    table: str,
    group_column: str,
    groups: int,
) -> None:
    """Acceptance F39: tool yang sama bekerja di kedua dataset demo tanpa perubahan kode."""
    config = project_config(dataset)

    sql = f"SELECT {group_column}, count(*) AS n FROM {table} GROUP BY 1 ORDER BY 1"
    describe = tool_call("describe_table", table=table)
    profile = tool_call("profile_table", table=table, columns=[group_column])
    query = tool_call("run_sql", sql=sql, name=f"{table} by {group_column}")

    described = await run_tool(registry, workspace, describe, config)
    profiled = await run_tool(registry, workspace, profile, config)
    queried = await run_tool(registry, workspace, query, config)

    assert f"Table public.{table}" in str(described.content)
    assert "Sample rows:" in str(described.content)
    assert f"distinct {groups}" in str(profiled.content)
    path = f"data/{table}_by_{group_column}.parquet"
    assert f"Saved {groups} rows x 2 columns to {path}" in str(queried.content)
    saved = pq.read_table(io.BytesIO(await workspace.read("t1", path)))
    assert saved.column_names == [group_column, "n"]
    assert saved.num_rows == groups


async def test_run_sql_caps_rows_and_says_so(
    registry: DataSourceRegistry, workspace: InMemoryWorkspace
) -> None:
    call = tool_call("run_sql", sql="SELECT * FROM readings", name="all readings")

    message = await run_tool(registry, workspace, call, project_config("sensors"), max_rows=10)

    assert "Saved 10 rows" in str(message.content)
    assert "cut at 10 rows" in str(message.content)
    saved = pq.read_table(io.BytesIO(await workspace.read("t1", "data/all_readings.parquet")))
    assert saved.num_rows == 10


async def test_rejected_sql_is_returned_to_the_model(
    registry: DataSourceRegistry, workspace: InMemoryWorkspace
) -> None:
    call = tool_call("run_sql", sql="DELETE FROM orders", name="x")

    message = await run_tool(registry, workspace, call, project_config("shop"))

    assert message.status == "error"
    assert "Only SELECT queries are allowed" in str(message.content)
    assert await workspace.list_files("t1") == []


async def test_sql_errors_are_returned_to_the_model(
    registry: DataSourceRegistry, workspace: InMemoryWorkspace
) -> None:
    call = tool_call("run_sql", sql="SELECT no_such_column FROM orders", name="x")

    message = await run_tool(registry, workspace, call, project_config("shop"))

    assert message.status == "error"
    assert "no_such_column" in str(message.content)
