import json
from collections.abc import Sequence

import httpx
import pytest
from langchain_core.tools import ToolException

from agent_service.agents.tools.web_search import (
    FIRECRAWL_SEARCH_URL,
    NO_RESULTS_TEXT,
    NOT_CONFIGURED_TEXT,
    WEB_SEARCH_MAX_RESULTS,
    WEB_SEARCH_TOOL_NAME,
    FirecrawlSearch,
    SearchError,
    SearchResult,
    UnconfiguredSearch,
    create_search_backend,
    create_web_search_tool,
    format_search_results,
    parse_firecrawl_results,
)

RESULTS = [
    SearchResult("LangGraph", "https://langchain.dev/langgraph", "Graph agents"),
    SearchResult("Untitled", "https://example.com", "No title"),
]
FIRECRAWL_BODY = {
    "success": True,
    "data": {
        "web": [
            {"url": "https://python.org", "title": "Python", "description": "Released 1991"},
            {"url": "https://example.com"},
        ]
    },
    "creditsUsed": 2,
}


class FakeSearch:
    """Backend tiruan yang merekam query dan mengembalikan hasil tetap."""

    def __init__(
        self, results: Sequence[SearchResult] = (), error: SearchError | None = None
    ) -> None:
        self.calls: list[tuple[str, int]] = []
        self._results = list(results)
        self._error = error

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        self.calls.append((query, max_results))
        if self._error is not None:
            raise self._error
        return self._results


def firecrawl(respond: httpx.MockTransport) -> FirecrawlSearch:
    return FirecrawlSearch("fc-test", transport=respond)


async def test_tool_returns_numbered_markdown_links() -> None:
    backend = FakeSearch(RESULTS)

    output = await create_web_search_tool(backend).ainvoke({"query": "langgraph"})

    assert output == (
        "1. [LangGraph](https://langchain.dev/langgraph)\n"
        "   Graph agents\n"
        "2. [Untitled](https://example.com)\n"
        "   No title"
    )
    assert backend.calls == [("langgraph", WEB_SEARCH_MAX_RESULTS)]


async def test_tool_passes_max_results() -> None:
    backend = FakeSearch()

    await create_web_search_tool(backend, max_results=2).ainvoke({"query": "x"})

    assert backend.calls == [("x", 2)]


async def test_tool_reports_no_results() -> None:
    output = await create_web_search_tool(FakeSearch()).ainvoke({"query": "nothing"})

    assert output == NO_RESULTS_TEXT


async def test_search_error_becomes_tool_exception() -> None:
    tool = create_web_search_tool(FakeSearch(error=SearchError("quota exceeded")))

    with pytest.raises(ToolException, match="quota exceeded"):
        await tool.ainvoke({"query": "x"})


async def test_unconfigured_backend_tells_model_search_is_off() -> None:
    tool = create_web_search_tool(UnconfiguredSearch())

    with pytest.raises(ToolException, match="FIRECRAWL_API_KEY"):
        await tool.ainvoke({"query": "x"})


def test_schema_exposes_only_query() -> None:
    tool = create_web_search_tool(FakeSearch())

    assert tool.name == WEB_SEARCH_TOOL_NAME
    assert list(tool.args) == ["query"]


def test_backend_choice_follows_api_key() -> None:
    assert isinstance(create_search_backend("fc-test"), FirecrawlSearch)
    assert isinstance(create_search_backend(None), UnconfiguredSearch)
    assert isinstance(create_search_backend(""), UnconfiguredSearch)


async def test_firecrawl_sends_authenticated_search_request() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=FIRECRAWL_BODY)

    results = await firecrawl(httpx.MockTransport(respond)).search("python release", 3)

    [request] = requests
    assert (request.method, str(request.url)) == ("POST", FIRECRAWL_SEARCH_URL)
    assert request.headers["authorization"] == "Bearer fc-test"
    assert json.loads(request.content) == {"query": "python release", "limit": 3}
    assert results == [
        SearchResult("Python", "https://python.org", "Released 1991"),
        SearchResult("Untitled", "https://example.com", ""),
    ]


@pytest.mark.parametrize("status", [401, 402, 429, 500])
async def test_firecrawl_http_errors_raise_search_error(status: int) -> None:
    backend = firecrawl(httpx.MockTransport(lambda request: httpx.Response(status, text="nope")))

    with pytest.raises(SearchError, match=f"Firecrawl returned {status}: nope"):
        await backend.search("x", 1)


async def test_firecrawl_connection_error_raises_search_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(SearchError, match="Firecrawl request failed"):
        await firecrawl(httpx.MockTransport(refuse)).search("x", 1)


async def test_firecrawl_invalid_json_raises_search_error() -> None:
    backend = firecrawl(httpx.MockTransport(lambda request: httpx.Response(200, text="<html>")))

    with pytest.raises(SearchError, match="Unexpected Firecrawl response"):
        await backend.search("x", 1)


@pytest.mark.parametrize(
    "payload",
    [{"success": True, "data": {}}, {"success": True, "data": {"web": None}}, {"data": []}],
)
def test_parse_tolerates_missing_web_results(payload: dict[str, object]) -> None:
    assert parse_firecrawl_results(payload) == []  # pyrefly: ignore[bad-argument-type]


def test_parse_rejects_non_object() -> None:
    with pytest.raises(ValueError):
        parse_firecrawl_results([1, 2])


def test_format_empty_list() -> None:
    assert format_search_results([]) == NO_RESULTS_TEXT
    assert NOT_CONFIGURED_TEXT.startswith("Web search is not configured")
