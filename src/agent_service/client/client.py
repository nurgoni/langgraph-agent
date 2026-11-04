"""`AgentClient`: akses ke agent service lewat HTTP, dengan method sync dan async (FR-17)."""

import logging
from types import TracebackType
from typing import Final, Self

import httpx
from pydantic import BaseModel, JsonValue

from agent_service.client.errors import AgentClientError
from agent_service.client.requests import (
    AgentReply,
    RequestSpec,
    parse_model,
    path_segment,
    raise_for_status,
    run_ids,
)
from agent_service.client.stream import AsyncStreamRun, StreamRun
from agent_service.schema.requests import (
    THREADS_LIMIT_DEFAULT,
    ChatHistoryInput,
    StreamInput,
    ThreadRenameInput,
    UserInput,
    UserThreadsQuery,
)
from agent_service.schema.responses import (
    ChatHistory,
    ChatMessage,
    ServiceMetadata,
    ThreadSummary,
    UserThreads,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL: Final = "http://localhost:8080"
DEFAULT_TIMEOUT_SECONDS: Final = 60.0
AUTHORIZATION_HEADER: Final = "Authorization"
BEARER_PREFIX: Final = "Bearer "


class AgentClient:
    """Client untuk agent service. Tidak ada request di konstruktor (FR-19).

    `agent_id=None` berarti route agent default (`/invoke`, `/stream`, dan seterusnya). Ganti
    `agent_id` kapan saja untuk berpindah agent. Satu koneksi HTTP dipakai ulang sampai `close()`
    atau `aclose()`, atau gunakan `with` / `async with`. Setiap method sync punya pasangan async
    berawalan `a` (`invoke` menjadi `ainvoke`, `stream` menjadi `astream`).

    >>> client = AgentClient(base_url="http://localhost:8080", agent_id="chatbot")
    >>> client.agent_id
    'chatbot'
    >>> client.close()
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        agent_id: str | None = None,
        auth_secret: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
        async_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Inisialisasi client tanpa menghubungi service.

        Args:
            base_url: URL service (`AGENT_URL`).
            agent_id: Agent tujuan, atau `None` untuk agent default service.
            auth_secret: Token bearer (`AUTH_SECRET`), jika service memakai auth.
            timeout: Batas waktu per operasi HTTP, dalam detik.
            transport: Transport httpx sync, misalnya `httpx.MockTransport` untuk test.
            async_transport: Transport httpx async.
        """
        self.agent_id = agent_id
        headers = {} if auth_secret is None else {AUTHORIZATION_HEADER: BEARER_PREFIX + auth_secret}
        self._http_client = httpx.Client(
            base_url=base_url, headers=headers, timeout=timeout, transport=transport
        )
        self._async_http_client = httpx.AsyncClient(
            base_url=base_url, headers=headers, timeout=timeout, transport=async_transport
        )
        self._info: ServiceMetadata | None = None

    def __enter__(self) -> Self:
        """Pakai client sync dalam blok `with`."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Tutup koneksi sync."""
        self.close()

    async def __aenter__(self) -> Self:
        """Pakai client async dalam blok `async with`."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Tutup koneksi async."""
        await self.aclose()

    def close(self) -> None:
        """Tutup koneksi HTTP sync."""
        self._http_client.close()

    async def aclose(self) -> None:
        """Tutup koneksi HTTP async."""
        await self._async_http_client.aclose()

    def get_info(self, refresh: bool = False) -> ServiceMetadata:
        """Agent, model, dan nilai default service. Diambil sekali lalu di-cache.

        Args:
            refresh: Ambil ulang dari service walau sudah ada di cache.

        Raises:
            AgentClientError: Request gagal.
        """
        if self._info is None or refresh:
            response = self._send(self._info_spec())
            self._info = parse_model(response, ServiceMetadata)
        return self._info

    def invoke(
        self,
        message: str,
        *,
        model: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_config: dict[str, JsonValue] | None = None,
    ) -> AgentReply:
        """Jalankan agent sampai selesai.

        Args:
            message: Pesan user, atau jawaban untuk pertanyaan interrupt.
            model: Model dari allowlist service. `None` berarti model default.
            thread_id: Thread yang dilanjutkan. `None` berarti thread baru.
            user_id: Pemilik thread. Wajib sama dengan run sebelumnya untuk melanjutkan thread.
            agent_config: Opsi agent sesuai `config_schema`-nya di `/info`.

        Returns:
            Jawaban akhir beserta `thread_id` dan `user_id` yang dipakai run.

        Raises:
            AgentClientError: Request gagal, misalnya 404 (agent/thread) atau 422 (input).
        """
        payload = UserInput(
            message=message,
            model=model,
            thread_id=thread_id,
            user_id=user_id,
            agent_config=agent_config or {},
        )
        response = self._send(self._invoke_spec(payload))
        thread, user = run_ids(response)
        return AgentReply(parse_model(response, ChatMessage), thread_id=thread, user_id=user)

    def stream(
        self,
        message: str,
        *,
        model: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_config: dict[str, JsonValue] | None = None,
        stream_tokens: bool = True,
    ) -> StreamRun:
        """Siapkan stream SSE. Request dikirim saat masuk `with`.

        Argumen sama dengan `invoke`, ditambah `stream_tokens` untuk frame `token`. Frame `error`
        dari service diteruskan sebagai `ErrorEvent`, bukan exception.

        Returns:
            Context manager yang punya `thread_id`/`user_id` dan bisa di-iterasi untuk event.
        """
        payload = StreamInput(
            message=message,
            model=model,
            thread_id=thread_id,
            user_id=user_id,
            agent_config=agent_config or {},
            stream_tokens=stream_tokens,
        )
        return StreamRun(self._http_client, self._stream_spec(payload))

    def get_history(self, thread_id: str, user_id: str) -> ChatHistory:
        """Semua message satu thread milik `user_id`.

        Raises:
            AgentClientError: 404 jika thread tidak ada atau milik user lain.
        """
        return parse_model(self._send(self._history_spec(thread_id, user_id)), ChatHistory)

    def get_threads(self, user_id: str, limit: int = THREADS_LIMIT_DEFAULT) -> UserThreads:
        """Thread milik `user_id` untuk agent ini, yang terakhir di-update lebih dulu.

        Raises:
            AgentClientError: Request gagal.
        """
        return parse_model(self._send(self._threads_spec(user_id, limit)), UserThreads)

    def rename_thread(self, thread_id: str, user_id: str, title: str) -> ThreadSummary:
        """Ganti judul thread.

        Raises:
            AgentClientError: 404 jika thread tidak ada atau milik user lain, 422 jika judul tidak
                valid.
        """
        spec = self._rename_spec(thread_id, user_id, title)
        return parse_model(self._send(spec), ThreadSummary)

    def delete_thread(self, thread_id: str, user_id: str) -> None:
        """Hapus thread beserta seluruh riwayatnya.

        Raises:
            AgentClientError: 404 jika thread tidak ada atau milik user lain.
        """
        self._send(self._delete_spec(thread_id, user_id))

    async def aget_info(self, refresh: bool = False) -> ServiceMetadata:
        """Versi async `get_info`. Cache dipakai bersama dengan versi sync."""
        if self._info is None or refresh:
            response = await self._asend(self._info_spec())
            self._info = parse_model(response, ServiceMetadata)
        return self._info

    async def ainvoke(
        self,
        message: str,
        *,
        model: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_config: dict[str, JsonValue] | None = None,
    ) -> AgentReply:
        """Versi async `invoke`."""
        payload = UserInput(
            message=message,
            model=model,
            thread_id=thread_id,
            user_id=user_id,
            agent_config=agent_config or {},
        )
        response = await self._asend(self._invoke_spec(payload))
        thread, user = run_ids(response)
        return AgentReply(parse_model(response, ChatMessage), thread_id=thread, user_id=user)

    def astream(
        self,
        message: str,
        *,
        model: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_config: dict[str, JsonValue] | None = None,
        stream_tokens: bool = True,
    ) -> AsyncStreamRun:
        """Versi async `stream`. Request dikirim saat masuk `async with`."""
        payload = StreamInput(
            message=message,
            model=model,
            thread_id=thread_id,
            user_id=user_id,
            agent_config=agent_config or {},
            stream_tokens=stream_tokens,
        )
        return AsyncStreamRun(self._async_http_client, self._stream_spec(payload))

    async def aget_history(self, thread_id: str, user_id: str) -> ChatHistory:
        """Versi async `get_history`."""
        response = await self._asend(self._history_spec(thread_id, user_id))
        return parse_model(response, ChatHistory)

    async def aget_threads(self, user_id: str, limit: int = THREADS_LIMIT_DEFAULT) -> UserThreads:
        """Versi async `get_threads`."""
        response = await self._asend(self._threads_spec(user_id, limit))
        return parse_model(response, UserThreads)

    async def arename_thread(self, thread_id: str, user_id: str, title: str) -> ThreadSummary:
        """Versi async `rename_thread`."""
        response = await self._asend(self._rename_spec(thread_id, user_id, title))
        return parse_model(response, ThreadSummary)

    async def adelete_thread(self, thread_id: str, user_id: str) -> None:
        """Versi async `delete_thread`."""
        await self._asend(self._delete_spec(thread_id, user_id))

    def _send(self, spec: RequestSpec) -> httpx.Response:
        """Kirim request sync dan pastikan statusnya 2xx.

        Raises:
            AgentClientError: Koneksi gagal atau status non-2xx.
        """
        logger.debug("%s %s", spec.method, spec.path)
        try:
            response = self._http_client.request(
                spec.method, spec.path, json=spec.json, params=spec.params
            )
        except httpx.RequestError as error:
            raise AgentClientError(f"{spec.method} {spec.path} failed: {error}") from error
        raise_for_status(response)
        return response

    async def _asend(self, spec: RequestSpec) -> httpx.Response:
        """Kirim request async dan pastikan statusnya 2xx.

        Raises:
            AgentClientError: Koneksi gagal atau status non-2xx.
        """
        logger.debug("%s %s", spec.method, spec.path)
        try:
            response = await self._async_http_client.request(
                spec.method, spec.path, json=spec.json, params=spec.params
            )
        except httpx.RequestError as error:
            raise AgentClientError(f"{spec.method} {spec.path} failed: {error}") from error
        raise_for_status(response)
        return response

    def _agent_path(self, suffix: str) -> str:
        """Path untuk agent terpilih, atau path agent default jika `agent_id` kosong."""
        if self.agent_id is None:
            return suffix
        return f"/{path_segment(self.agent_id)}{suffix}"

    def _info_spec(self) -> RequestSpec:
        """Request `GET /info`."""
        return RequestSpec("GET", "/info")

    def _invoke_spec(self, payload: UserInput) -> RequestSpec:
        """Request `POST /{agent_id}/invoke`."""
        return RequestSpec("POST", self._agent_path("/invoke"), json=_json_body(payload))

    def _stream_spec(self, payload: StreamInput) -> RequestSpec:
        """Request `POST /{agent_id}/stream`."""
        return RequestSpec("POST", self._agent_path("/stream"), json=_json_body(payload))

    def _history_spec(self, thread_id: str, user_id: str) -> RequestSpec:
        """Request `POST /{agent_id}/history`."""
        body = _json_body(ChatHistoryInput(thread_id=thread_id, user_id=user_id))
        return RequestSpec("POST", self._agent_path("/history"), json=body)

    def _threads_spec(self, user_id: str, limit: int) -> RequestSpec:
        """Request `GET /{agent_id}/threads`, dengan `limit` divalidasi schema."""
        query = UserThreadsQuery(user_id=user_id, limit=limit)
        params: dict[str, str | int] = {"user_id": query.user_id, "limit": query.limit}
        return RequestSpec("GET", self._agent_path("/threads"), params=params)

    def _rename_spec(self, thread_id: str, user_id: str, title: str) -> RequestSpec:
        """Request `PATCH /{agent_id}/threads/{thread_id}`."""
        body = _json_body(ThreadRenameInput(user_id=user_id, title=title))
        return RequestSpec("PATCH", self._thread_path(thread_id), json=body)

    def _delete_spec(self, thread_id: str, user_id: str) -> RequestSpec:
        """Request `DELETE /{agent_id}/threads/{thread_id}`."""
        return RequestSpec("DELETE", self._thread_path(thread_id), params={"user_id": user_id})

    def _thread_path(self, thread_id: str) -> str:
        """Path satu thread milik agent terpilih."""
        return self._agent_path(f"/threads/{path_segment(thread_id)}")


def _json_body(payload: BaseModel) -> dict[str, JsonValue]:
    """Body JSON dari schema request, tanpa field yang kosong."""
    return payload.model_dump(mode="json", exclude_none=True)
