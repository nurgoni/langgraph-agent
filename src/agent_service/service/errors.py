"""Pemetaan exception domain ke response HTTP berbentuk `{"detail": str}` (NFR-6).

Error validasi request (422 dari FastAPI) tetap memakai format bawaan: `detail` berupa list per
field, supaya client bisa menandai field yang salah.
"""

import logging
from collections.abc import Mapping
from typing import Final

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from agent_service.agents.errors import AgentNotFoundError, AgentUnavailableError
from agent_service.llm.factory import ModelNotConfiguredError, UnknownModelError
from agent_service.service.thread_access import ThreadNotFoundError

logger = logging.getLogger(__name__)

DOMAIN_ERROR_STATUS: Final[Mapping[type[Exception], int]] = {
    AgentNotFoundError: status.HTTP_404_NOT_FOUND,
    ThreadNotFoundError: status.HTTP_404_NOT_FOUND,
    AgentUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    UnknownModelError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ModelNotConfiguredError: status.HTTP_503_SERVICE_UNAVAILABLE,
}
INTERNAL_ERROR_DETAIL: Final = "Internal server error"


def register_exception_handlers(app: FastAPI) -> None:
    """Pasang handler untuk setiap exception domain dan untuk error tak terduga.

    Args:
        app: App yang akan dipasangi handler.

    >>> app = FastAPI()
    >>> register_exception_handlers(app)
    >>> AgentNotFoundError in app.exception_handlers
    True
    """
    for error_class in DOMAIN_ERROR_STATUS:
        app.add_exception_handler(error_class, handle_domain_error)
    app.add_exception_handler(Exception, handle_unexpected_error)


async def handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    """Ubah exception domain menjadi response dengan status dari `DOMAIN_ERROR_STATUS`.

    Args:
        request: Request yang gagal.
        exc: Exception domain yang terdaftar.

    Returns:
        Response `{"detail": <pesan exception>}`.
    """
    status_code = status_code_for(exc)
    if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        logger.warning("%s %s failed: %s", request.method, request.url.path, exc)
    return JSONResponse({"detail": str(exc)}, status_code=status_code)


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Batas sistem: catat error tak terduga dan jawab 500 tanpa membocorkan detailnya.

    Args:
        request: Request yang gagal.
        exc: Exception apa pun yang tidak ditangani handler lain.

    Returns:
        Response 500 `{"detail": "Internal server error"}`.
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        {"detail": INTERNAL_ERROR_DETAIL}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )


def status_code_for(exc: Exception) -> int:
    """Cari status HTTP untuk exception, termasuk subclass dari error yang terdaftar.

    >>> status_code_for(AgentNotFoundError("x"))
    404
    >>> status_code_for(RuntimeError("x"))
    500
    """
    for error_class in type(exc).__mro__:
        status_code = DOMAIN_ERROR_STATUS.get(error_class)
        if status_code is not None:
            return status_code
    return status.HTTP_500_INTERNAL_SERVER_ERROR
