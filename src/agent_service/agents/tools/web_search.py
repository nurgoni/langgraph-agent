"""Tool web search berbasis Firecrawl Search API.

Tanpa API key, tool tetap dipasang tapi menjawab "not configured", supaya agent tetap berjalan
(misalnya di CI atau stack Docker default) dan model bisa menjawab tanpa pencarian.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol

import httpx
from langchain_core.tools import BaseTool, ToolException, tool
from pydantic import JsonValue

logger = logging.getLogger(__name__)

WEB_SEARCH_TOOL_NAME: Final = "web_search"
WEB_SEARCH_MAX_RESULTS: Final = 5
NO_RESULTS_TEXT: Final = "No results found."
UNTITLED_RESULT: Final = "Untitled"
NOT_CONFIGURED_TEXT: Final = (
    "Web search is not configured on this server (FIRECRAWL_API_KEY is empty). "
    "Answer from your own knowledge and say that you could not search the web."
)

FIRECRAWL_SEARCH_URL: Final = "https://api.firecrawl.dev/v2/search"
FIRECRAWL_TIMEOUT_SECONDS: Final = 30.0
AUTHORIZATION_HEADER: Final = "Authorization"
BEARER_PREFIX: Final = "Bearer "
ERROR_BODY_PREVIEW_CHARS: Final = 200


class SearchError(Exception):
    """Pencarian gagal: belum dikonfigurasi, ditolak provider, atau koneksi bermasalah."""


@dataclass(frozen=True)
class SearchResult:
    """Satu hasil pencarian yang sudah dinormalisasi dari format provider."""

    title: str
    url: str
    snippet: str


class SearchBackend(Protocol):
    """Mesin pencari yang dipakai tool. Implementasi produksi: `FirecrawlSearch`."""

    async def search(self, query: str, max_results: int) -> Sequence[SearchResult]:
        """Cari `query` dan kembalikan paling banyak `max_results` hasil.

        Raises:
            SearchError: Jika pencarian tidak bisa dilakukan.
        """
        ...


class FirecrawlSearch:
    """`SearchBackend` di atas `POST /v2/search` Firecrawl, dengan satu client HTTP dipakai ulang.

    Hanya mengambil hasil web (judul, URL, deskripsi), tanpa scraping halaman, supaya hemat kredit.
    """

    def __init__(
        self,
        api_key: str,
        search_url: str = FIRECRAWL_SEARCH_URL,
        timeout: float = FIRECRAWL_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Inisialisasi backend tanpa membuka koneksi.

        Args:
            api_key: Firecrawl API key (`FIRECRAWL_API_KEY`).
            search_url: Endpoint search Firecrawl.
            timeout: Batas waktu per request, dalam detik.
            transport: Transport httpx, misalnya `httpx.MockTransport` untuk test.
        """
        self._search_url = search_url
        self._client = httpx.AsyncClient(
            headers={AUTHORIZATION_HEADER: BEARER_PREFIX + api_key},
            timeout=timeout,
            transport=transport,
        )

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Cari di web lewat Firecrawl.

        Raises:
            SearchError: Koneksi gagal, status non-2xx (misalnya key salah atau kredit habis),
                atau respons tidak sesuai format.
        """
        try:
            response = await self._client.post(
                self._search_url, json={"query": query, "limit": max_results}
            )
        except httpx.RequestError as error:
            raise SearchError(f"Firecrawl request failed: {error}") from error
        if not response.is_success:
            preview = response.text[:ERROR_BODY_PREVIEW_CHARS]
            raise SearchError(f"Firecrawl returned {response.status_code}: {preview}")
        try:
            return parse_firecrawl_results(response.json())
        except ValueError as error:
            raise SearchError(f"Unexpected Firecrawl response: {error}") from error


class UnconfiguredSearch:
    """`SearchBackend` pengganti saat API key kosong: setiap pencarian menjawab not configured."""

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Selalu gagal dengan pesan yang bisa dipahami model.

        Raises:
            SearchError: Selalu, berisi `NOT_CONFIGURED_TEXT`.
        """
        raise SearchError(NOT_CONFIGURED_TEXT)


def parse_firecrawl_results(payload: JsonValue) -> list[SearchResult]:
    """Ambil hasil web dari respons Firecrawl (`data.web[]` berisi `url`, `title`, `description`).

    Raises:
        ValueError: Jika `payload` bukan object JSON.

    >>> payload = {"success": True, "data": {"web": [
    ...     {"url": "https://x.dev", "title": "X", "description": "Docs"}]}}
    >>> parse_firecrawl_results(payload)
    [SearchResult(title='X', url='https://x.dev', snippet='Docs')]
    """
    if not isinstance(payload, dict):
        raise ValueError("response is not a JSON object")
    data = payload.get("data")
    web = data.get("web") if isinstance(data, dict) else None
    if not isinstance(web, list):
        return []
    results: list[SearchResult] = []
    for item in web:
        if isinstance(item, dict):
            results.append(_to_search_result(item))
    return results


def _to_search_result(item: dict[str, JsonValue]) -> SearchResult:
    """Normalisasi satu item `data.web` Firecrawl."""
    return SearchResult(
        title=str(item.get("title") or UNTITLED_RESULT),
        url=str(item.get("url") or ""),
        snippet=str(item.get("description") or ""),
    )


def create_search_backend(api_key: str | None) -> SearchBackend:
    """Backend pencarian sesuai konfigurasi: Firecrawl jika ada key, selain itu tanpa pencarian.

    Function, bukan class: factory pemilih implementasi, tanpa state.

    >>> type(create_search_backend(None)).__name__
    'UnconfiguredSearch'
    """
    if not api_key:
        logger.warning("FIRECRAWL_API_KEY is not set: the web_search tool will be unavailable")
        return UnconfiguredSearch()
    return FirecrawlSearch(api_key)


def format_search_results(results: Sequence[SearchResult]) -> str:
    """Ubah hasil pencarian menjadi daftar bernomor dengan link markdown untuk dikutip model.

    >>> print(format_search_results([SearchResult("LangGraph", "https://x.dev", "Docs")]))
    1. [LangGraph](https://x.dev)
       Docs
    >>> format_search_results([])
    'No results found.'
    """
    if not results:
        return NO_RESULTS_TEXT
    lines: list[str] = []
    for number, result in enumerate(results, start=1):
        lines.append(f"{number}. [{result.title}]({result.url})")
        lines.append(f"   {result.snippet}")
    return "\n".join(lines)


def create_web_search_tool(
    backend: SearchBackend, max_results: int = WEB_SEARCH_MAX_RESULTS
) -> BaseTool:
    """Buat tool `web_search` yang memakai `backend`.

    Function factory, bukan class: `@tool` harus membungkus function, dan closure ini hanya
    menyuntikkan backend supaya test tidak membutuhkan network.

    Args:
        backend: Mesin pencari, biasanya dari `create_search_backend`.
        max_results: Jumlah hasil per pencarian.

    Returns:
        Tool async yang bisa dipasang ke agent.
    """

    @tool(WEB_SEARCH_TOOL_NAME)
    async def web_search(query: str) -> str:
        """Search the web for current information.

        Returns numbered results with markdown links, titles and short snippets.
        """
        # Docstring berbahasa Inggris karena dikirim ke LLM sebagai deskripsi tool.
        try:
            results = await backend.search(query, max_results)
        except SearchError as error:
            raise ToolException(f"Web search for {query!r} failed: {error}") from error
        return format_search_results(results)

    return web_search


if __name__ == "__main__":
    import asyncio

    from agent_service.core.settings import Settings

    secret = Settings(use_fake_model=True).firecrawl_api_key
    key = secret.get_secret_value() if secret is not None else None
    demo_tool = create_web_search_tool(create_search_backend(key))
    print(asyncio.run(demo_tool.ainvoke({"query": "LangGraph"})))
