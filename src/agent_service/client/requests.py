"""Bagian request dan respons yang dipakai bersama oleh method sync dan async `AgentClient`."""

from dataclasses import dataclass, field
from typing import Final
from urllib.parse import quote

import httpx
from pydantic import BaseModel, JsonValue, ValidationError

from agent_service.client.errors import AgentClientError, ServiceUnreachableError
from agent_service.schema.headers import THREAD_ID_HEADER, USER_ID_HEADER
from agent_service.schema.responses import ChatMessage

DETAIL_KEY: Final = "detail"
# Error httpx yang berarti koneksi tidak pernah terbentuk, berbeda dari koneksi yang putus.
CONNECT_ERRORS: Final = (httpx.ConnectError, httpx.ConnectTimeout)
URL_SAFE_CHARS: Final = ""


@dataclass(frozen=True)
class RequestSpec:
    """Satu request HTTP yang siap dikirim, terlepas dari client sync atau async."""

    method: str
    path: str
    json: dict[str, JsonValue] | None = None
    params: dict[str, str | int] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentReply:
    """Hasil `invoke`: jawaban akhir beserta ID yang dipakai run (FR-13).

    Kirim `thread_id` dan `user_id` lagi untuk melanjutkan thread yang sama.
    """

    message: ChatMessage
    thread_id: str
    user_id: str


def path_segment(value: str) -> str:
    """Escape satu segmen path URL, supaya ID berisi `/` atau spasi tetap aman.

    >>> path_segment("a/b c")
    'a%2Fb%20c'
    """
    return quote(value, safe=URL_SAFE_CHARS)


def raise_for_status(response: httpx.Response) -> None:
    """Ubah respons non-2xx menjadi `AgentClientError` dengan status dan `detail` dari service.

    Body respons harus sudah dibaca. Untuk respons stream, panggil `read()` lebih dulu.

    Raises:
        AgentClientError: Jika status bukan 2xx.
    """
    if response.is_success:
        return
    detail = response_detail(response)
    request = response.request
    raise AgentClientError(
        f"{request.method} {request.url.path} failed with {response.status_code}: {detail}",
        status_code=response.status_code,
        detail=detail,
    )


def response_detail(response: httpx.Response) -> JsonValue:
    """Field `detail` dari body error JSON, atau teks body jika bukan JSON."""
    try:
        body = response.json()
    except ValueError:
        return response.text
    if isinstance(body, dict) and DETAIL_KEY in body:
        return body[DETAIL_KEY]
    return body


def parse_model[ModelT: BaseModel](response: httpx.Response, model_type: type[ModelT]) -> ModelT:
    """Validasi body respons dengan schema API.

    Raises:
        AgentClientError: Jika body tidak cocok dengan schema (versi service berbeda).
    """
    try:
        return model_type.model_validate_json(response.content)
    except ValidationError as error:
        raise AgentClientError(
            f"Unexpected response for {model_type.__name__}", status_code=response.status_code
        ) from error


def run_ids(response: httpx.Response) -> tuple[str, str]:
    """Ambil `(thread_id, user_id)` dari header respons `/invoke` atau `/stream`.

    Raises:
        AgentClientError: Jika header tidak ada (service versi lama atau proxy membuangnya).
    """
    thread_id = response.headers.get(THREAD_ID_HEADER)
    user_id = response.headers.get(USER_ID_HEADER)
    if thread_id is None or user_id is None:
        raise AgentClientError(
            f"Response is missing {THREAD_ID_HEADER}/{USER_ID_HEADER} headers",
            status_code=response.status_code,
        )
    return thread_id, user_id


def request_error(error: httpx.RequestError, context: str) -> AgentClientError:
    """Bungkus error httpx. Gagal membuka koneksi menjadi `ServiceUnreachableError`.

    Args:
        error: Error dari httpx.
        context: Ringkasan request, misalnya `"POST /chatbot/invoke"`.

    Returns:
        Error untuk dilempar pemanggil dengan `raise ... from error`.
    """
    message = f"{context} failed: {error}"
    if isinstance(error, CONNECT_ERRORS):
        return ServiceUnreachableError(message)
    return AgentClientError(message)
