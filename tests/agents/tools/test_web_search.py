from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from ddgs.exceptions import DDGSException
from langchain_core.tools import ToolException

from agent_service.agents.tools.web_search import (
    NO_RESULTS_TEXT,
    WEB_SEARCH_MAX_RESULTS,
    WEB_SEARCH_TOOL_NAME,
    create_web_search_tool,
    format_search_results,
)

RESULTS = [
    {"title": "LangGraph", "href": "https://langchain.dev/langgraph", "body": "Graph agents"},
    {"title": "", "href": "https://example.com", "body": "No title"},
]


class FakeSearch:
    """Backend tiruan yang merekam query dan mengembalikan hasil tetap."""

    def __init__(
        self,
        results: Sequence[Mapping[str, Any]] = (),  # Any: hasil mentah mesin pencari
        error: Exception | None = None,
    ) -> None:
        self.calls: list[tuple[str, int]] = []
        self._results = list(results)
        self._error = error

    def text(self, query: str, max_results: int) -> Sequence[Mapping[str, Any]]:
        self.calls.append((query, max_results))
        if self._error is not None:
            raise self._error
        return self._results


async def test_returns_numbered_markdown_links() -> None:
    backend = FakeSearch(RESULTS)
    web_search = create_web_search_tool(backend)

    output = await web_search.ainvoke({"query": "langgraph"})

    assert output == (
        "1. [LangGraph](https://langchain.dev/langgraph)\n"
        "   Graph agents\n"
        "2. [Untitled](https://example.com)\n"
        "   No title"
    )
    assert backend.calls == [("langgraph", WEB_SEARCH_MAX_RESULTS)]


async def test_max_results_is_passed_to_backend() -> None:
    backend = FakeSearch()

    await create_web_search_tool(backend, max_results=2).ainvoke({"query": "x"})

    assert backend.calls == [("x", 2)]


async def test_no_results_is_explicit() -> None:
    output = await create_web_search_tool(FakeSearch()).ainvoke({"query": "nothing"})

    assert output == NO_RESULTS_TEXT


async def test_search_failure_becomes_tool_exception() -> None:
    web_search = create_web_search_tool(FakeSearch(error=DDGSException("rate limited")))

    with pytest.raises(ToolException, match="rate limited"):
        await web_search.ainvoke({"query": "x"})


def test_schema_exposes_only_query() -> None:
    web_search = create_web_search_tool(FakeSearch())

    assert web_search.name == WEB_SEARCH_TOOL_NAME
    assert list(web_search.args) == ["query"]


def test_default_backend_is_created_without_network() -> None:
    assert create_web_search_tool().name == WEB_SEARCH_TOOL_NAME


def test_format_handles_missing_fields() -> None:
    assert format_search_results([{}]) == "1. [Untitled]()\n   "
