"""Satu request `/stream` sebagai context manager (sync dan async): ID run, lalu event."""

from collections.abc import AsyncIterator, Iterator
from contextlib import AsyncExitStack, ExitStack
from types import TracebackType
from typing import Self

import httpx

from agent_service.client.errors import AgentClientError
from agent_service.client.requests import RequestSpec, raise_for_status, run_ids
from agent_service.client.sse import SseParser
from agent_service.schema.stream import StreamEvent


class StreamNotStartedError(AgentClientError):
    """Stream dipakai di luar blok `with`."""


class StreamRun:
    """Stream sync. Request dikirim saat masuk `with`, bukan saat objek dibuat.

    Contoh::

        with client.stream("Halo") as run:
            print(run.thread_id)
            for event in run:
                ...
    """

    def __init__(self, http_client: httpx.Client, spec: RequestSpec) -> None:
        """Inisialisasi stream tanpa mengirim request.

        Args:
            http_client: Client httpx milik `AgentClient`.
            spec: Request `/stream`.
        """
        self._http_client = http_client
        self._spec = spec
        self._exit_stack = ExitStack()
        self._response: httpx.Response | None = None
        self._thread_id: str | None = None
        self._user_id: str | None = None

    @property
    def thread_id(self) -> str:
        """ID thread yang dipakai run, termasuk ID yang dibuat service."""
        return _require_started(self._thread_id)

    @property
    def user_id(self) -> str:
        """ID user yang dipakai run, termasuk ID yang dibuat service."""
        return _require_started(self._user_id)

    def __enter__(self) -> Self:
        """Kirim request dan baca header ID.

        Raises:
            AgentClientError: Status non-2xx (misalnya 404/422 sebelum stream dimulai) atau koneksi
                gagal.
        """
        try:
            response = self._exit_stack.enter_context(
                self._http_client.stream(self._spec.method, self._spec.path, json=self._spec.json)
            )
            # Body error (detail 404/422) hanya bisa dibaca setelah di-load dari stream.
            if response.is_error:
                response.read()
        except httpx.RequestError as error:
            self._exit_stack.close()
            raise AgentClientError(f"Stream request failed: {error}") from error
        self._start(response)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Tutup koneksi stream."""
        self._exit_stack.close()

    def __iter__(self) -> Iterator[StreamEvent]:
        """Event `token`, `message`, dan `error` sampai `[DONE]`.

        Raises:
            AgentClientError: Koneksi terputus, frame tidak valid, atau stream berakhir tanpa
                `[DONE]`.
        """
        parser = SseParser()
        for line in self._lines():
            event = parser.feed_line(line)
            if event is not None:
                yield event
            if parser.done:
                return
        parser.finish()

    def _start(self, response: httpx.Response) -> None:
        """Simpan respons dan ID run, atau tutup koneksi jika status error."""
        try:
            raise_for_status(response)
            self._thread_id, self._user_id = run_ids(response)
        except AgentClientError:
            self._exit_stack.close()
            raise
        self._response = response

    def _lines(self) -> Iterator[str]:
        """Baris body respons, dengan error koneksi dibungkus `AgentClientError`."""
        response = _require_started(self._response)
        try:
            yield from response.iter_lines()
        except httpx.RequestError as error:
            raise AgentClientError(f"Stream interrupted: {error}") from error


class AsyncStreamRun:
    """Stream async. Request dikirim saat masuk `async with`, bukan saat objek dibuat.

    Contoh::

        async with client.astream("Halo") as run:
            print(run.thread_id)
            async for event in run:
                ...
    """

    def __init__(self, http_client: httpx.AsyncClient, spec: RequestSpec) -> None:
        """Inisialisasi stream tanpa mengirim request.

        Args:
            http_client: Client httpx async milik `AgentClient`.
            spec: Request `/stream`.
        """
        self._http_client = http_client
        self._spec = spec
        self._exit_stack = AsyncExitStack()
        self._response: httpx.Response | None = None
        self._thread_id: str | None = None
        self._user_id: str | None = None

    @property
    def thread_id(self) -> str:
        """ID thread yang dipakai run, termasuk ID yang dibuat service."""
        return _require_started(self._thread_id)

    @property
    def user_id(self) -> str:
        """ID user yang dipakai run, termasuk ID yang dibuat service."""
        return _require_started(self._user_id)

    async def __aenter__(self) -> Self:
        """Kirim request dan baca header ID.

        Raises:
            AgentClientError: Status non-2xx (misalnya 404/422 sebelum stream dimulai) atau koneksi
                gagal.
        """
        try:
            response = await self._exit_stack.enter_async_context(
                self._http_client.stream(self._spec.method, self._spec.path, json=self._spec.json)
            )
            # Body error (detail 404/422) hanya bisa dibaca setelah di-load dari stream.
            if response.is_error:
                await response.aread()
        except httpx.RequestError as error:
            await self._exit_stack.aclose()
            raise AgentClientError(f"Stream request failed: {error}") from error
        await self._start(response)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Tutup koneksi stream."""
        await self._exit_stack.aclose()

    async def __aiter__(self) -> AsyncIterator[StreamEvent]:
        """Event `token`, `message`, dan `error` sampai `[DONE]`.

        Raises:
            AgentClientError: Koneksi terputus, frame tidak valid, atau stream berakhir tanpa
                `[DONE]`.
        """
        parser = SseParser()
        async for line in self._lines():
            event = parser.feed_line(line)
            if event is not None:
                yield event
            if parser.done:
                return
        parser.finish()

    async def _start(self, response: httpx.Response) -> None:
        """Simpan respons dan ID run, atau tutup koneksi jika status error."""
        try:
            raise_for_status(response)
            self._thread_id, self._user_id = run_ids(response)
        except AgentClientError:
            await self._exit_stack.aclose()
            raise
        self._response = response

    async def _lines(self) -> AsyncIterator[str]:
        """Baris body respons, dengan error koneksi dibungkus `AgentClientError`."""
        response = _require_started(self._response)
        try:
            async for line in response.aiter_lines():
                yield line
        except httpx.RequestError as error:
            raise AgentClientError(f"Stream interrupted: {error}") from error


def _require_started[ValueT](value: ValueT | None) -> ValueT:
    """Nilai yang baru ada setelah masuk `with`.

    Raises:
        StreamNotStartedError: Jika stream belum dimulai.
    """
    if value is None:
        raise StreamNotStartedError("Use the stream inside a 'with' block")
    return value
