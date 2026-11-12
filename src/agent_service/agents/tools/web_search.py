"""Tool web search berbasis DuckDuckGo (`ddgs`), tanpa API key."""

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any, Final, Protocol

from ddgs import DDGS
from ddgs.exceptions import DDGSException
from langchain_core.tools import BaseTool, ToolException, tool

WEB_SEARCH_TOOL_NAME: Final = "web_search"
WEB_SEARCH_MAX_RESULTS: Final = 5
NO_RESULTS_TEXT: Final = "No results found."
UNTITLED_RESULT: Final = "Untitled"


class SearchBackend(Protocol):
    """Mesin pencari yang dipakai tool. `DDGS` memenuhi protokol ini, begitu juga fake di test."""

    def text(
        self, query: str, max_results: int
    ) -> Sequence[Mapping[str, Any]]:  # Any: hasil mentah mesin pencari
        """Cari `query` dan kembalikan hasil dengan kunci `title`, `href`, dan `body`."""
        ...


class DuckDuckGoSearch:
    """Adapter `SearchBackend` di atas `ddgs.DDGS`. Tidak membuka koneksi saat dibuat."""

    def __init__(self) -> None:
        """Buat client DuckDuckGo yang dipakai ulang untuk semua pencarian."""
        self._client = DDGS()

    def text(
        self, query: str, max_results: int
    ) -> Sequence[Mapping[str, Any]]:  # Any: hasil mentah mesin pencari
        """Cari `query` di DuckDuckGo.

        Raises:
            DDGSException: Jika pencarian gagal (misalnya rate limit atau koneksi).
        """
        return self._client.text(query, max_results=max_results)


def format_search_results(results: Sequence[Mapping[str, Any]]) -> str:  # Any: hasil mentah
    """Ubah hasil pencarian menjadi daftar bernomor dengan link markdown untuk dikutip model.

    >>> result = {"title": "LangGraph", "href": "https://x.dev", "body": "Docs"}
    >>> print(format_search_results([result]))
    1. [LangGraph](https://x.dev)
       Docs
    >>> format_search_results([])
    'No results found.'
    """
    if not results:
        return NO_RESULTS_TEXT
    lines: list[str] = []
    for number, result in enumerate(results, start=1):
        title = result.get("title") or UNTITLED_RESULT
        lines.append(f"{number}. [{title}]({result.get('href', '')})")
        lines.append(f"   {result.get('body', '')}")
    return "\n".join(lines)


def create_web_search_tool(
    backend: SearchBackend | None = None, max_results: int = WEB_SEARCH_MAX_RESULTS
) -> BaseTool:
    """Buat tool `web_search` yang memakai `backend`, dibuat sekali lalu dipakai ulang.

    Function factory, bukan class: `@tool` harus membungkus function, dan closure ini hanya
    menyuntikkan backend supaya test tidak membutuhkan network.

    Args:
        backend: Mesin pencari. Default: `DuckDuckGoSearch`.
        max_results: Jumlah hasil per pencarian.

    Returns:
        Tool async yang bisa dipasang ke agent.
    """
    search_backend = DuckDuckGoSearch() if backend is None else backend

    @tool(WEB_SEARCH_TOOL_NAME)
    async def web_search(query: str) -> str:
        """Search the web for current information.

        Returns numbered results with markdown links, titles and short snippets.
        """
        # Docstring berbahasa Inggris karena dikirim ke LLM sebagai deskripsi tool.
        try:
            # `text()` sinkron dan memakai network, jadi dijalankan di thread terpisah.
            results = await asyncio.to_thread(search_backend.text, query, max_results=max_results)
        except DDGSException as error:
            raise ToolException(f"Web search for {query!r} failed: {error}") from error
        return format_search_results(results)

    return web_search


if __name__ == "__main__":
    print(asyncio.run(create_web_search_tool().ainvoke({"query": "LangGraph"})))
