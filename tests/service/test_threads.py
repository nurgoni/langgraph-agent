import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import CheckpointTuple
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent_service.agents.base import AgentGraph
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.llm.fake import FakeModel
from agent_service.memory.checkpointer import CheckpointerProvider
from agent_service.schema.requests import TITLE_MAX_LENGTH
from agent_service.service.thread_access import run_metadata
from agent_service.service.threads import DEFAULT_THREAD_TITLE, ThreadRepository, thread_title

USER_A = "user-a"
USER_B = "user-b"


@pytest.fixture
async def saver(tmp_path: Path) -> AsyncIterator[AsyncSqliteSaver]:
    async with CheckpointerProvider(tmp_path / "threads.db") as checkpointer:
        yield checkpointer


@pytest.fixture
def graph(saver: AsyncSqliteSaver) -> AgentGraph:
    return ChatbotAgent().build(FakeModel(), saver)


async def send(
    graph: AgentGraph, thread_id: str, user_id: str, message: str, agent_id: str = "chatbot"
) -> None:
    config: RunnableConfig = {
        "configurable": {"thread_id": thread_id},
        "metadata": run_metadata(user_id, agent_id),
    }
    await graph.ainvoke({"messages": [HumanMessage(message)]}, config)


async def test_threads_are_isolated_per_user(graph: AgentGraph, saver: AsyncSqliteSaver) -> None:
    await send(graph, "a1", USER_A, "punya A")
    await send(graph, "b1", USER_B, "punya B")

    threads = await ThreadRepository(saver).list_threads(USER_A, "chatbot", limit=10)

    assert [thread.thread_id for thread in threads] == ["a1"]


async def test_threads_are_isolated_per_agent(graph: AgentGraph, saver: AsyncSqliteSaver) -> None:
    await send(graph, "a1", USER_A, "lewat chatbot")
    await send(graph, "a2", USER_A, "lewat agent lain", agent_id="other")

    threads = await ThreadRepository(saver).list_threads(USER_A, "chatbot", limit=10)

    assert [thread.thread_id for thread in threads] == ["a1"]


async def test_most_recently_updated_thread_comes_first(
    graph: AgentGraph, saver: AsyncSqliteSaver
) -> None:
    await send(graph, "old", USER_A, "pertama")
    await send(graph, "new", USER_A, "kedua")
    await send(graph, "old", USER_A, "lanjut thread lama")

    threads = await ThreadRepository(saver).list_threads(USER_A, "chatbot", limit=10)

    assert [thread.thread_id for thread in threads] == ["old", "new"]


async def test_summary_has_title_agent_and_update_time(
    graph: AgentGraph, saver: AsyncSqliteSaver
) -> None:
    await send(graph, "a1", USER_A, "Tolong ringkas dokumen")
    await send(graph, "a1", USER_A, "Pesan kedua")

    [thread] = await ThreadRepository(saver).list_threads(USER_A, "chatbot", limit=10)

    assert thread.title == "Tolong ringkas dokumen"
    assert thread.agent_id == "chatbot"
    assert thread.updated_at is not None


async def test_limit_caps_result(graph: AgentGraph, saver: AsyncSqliteSaver) -> None:
    for index in range(3):
        await send(graph, f"t{index}", USER_A, "halo")

    threads = await ThreadRepository(saver).list_threads(USER_A, "chatbot", limit=2)

    assert [thread.thread_id for thread in threads] == ["t2", "t1"]


async def test_paging_collects_threads_across_pages(
    graph: AgentGraph, saver: AsyncSqliteSaver
) -> None:
    for index in range(5):
        await send(graph, f"t{index}", USER_A, "halo")

    repository = ThreadRepository(saver, page_size=2)
    threads = await repository.list_threads(USER_A, "chatbot", limit=10)

    assert len(threads) == 5


async def test_max_threads_bounds_scan(graph: AgentGraph, saver: AsyncSqliteSaver) -> None:
    for index in range(4):
        await send(graph, f"t{index}", USER_A, "halo")

    repository = ThreadRepository(saver, page_size=2, max_threads=2)
    threads = await repository.list_threads(USER_A, "chatbot", limit=10)

    assert [thread.thread_id for thread in threads] == ["t3", "t2"]


async def test_unknown_user_has_no_threads(saver: AsyncSqliteSaver) -> None:
    assert await ThreadRepository(saver).list_threads("nobody", "chatbot", limit=10) == []


def test_title_is_truncated() -> None:
    title = thread_title([HumanMessage("x" * (TITLE_MAX_LENGTH + 10))])

    assert len(title) == TITLE_MAX_LENGTH


def test_title_falls_back_without_human_message() -> None:
    assert thread_title([]) == DEFAULT_THREAD_TITLE


class OwnerFilterIgnoringSaver(AsyncSqliteSaver):
    """Saver rusak yang hanya memfilter step, untuk menguji cek ulang pemilik di repository."""

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,  # Any: signature induk
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        async for checkpoint in super().alist(
            config, filter={"step": -1}, before=before, limit=limit
        ):
            yield checkpoint


async def test_owner_is_rechecked_when_saver_ignores_filter(
    graph: AgentGraph, saver: AsyncSqliteSaver, caplog: pytest.LogCaptureFixture
) -> None:
    await send(graph, "a1", USER_A, "punya A")
    await send(graph, "b1", USER_B, "punya B")
    leaky_saver = OwnerFilterIgnoringSaver(saver.conn)

    with caplog.at_level(logging.WARNING):
        threads = await ThreadRepository(leaky_saver).list_threads(USER_A, "chatbot", limit=10)

    assert [thread.thread_id for thread in threads] == ["a1"]
    assert "Skipping thread b1" in caplog.text
