"""Endpoint `/artifacts` (FR-46, keputusan user F35): upload, unduh, dan hapus file milik user.

Unduhan selalu `Content-Disposition: attachment` dengan `nosniff` dan CSP `sandbox`, jadi file
HTML atau SVG tidak pernah dirender di origin aplikasi. Preview di frontend memakai fetch → blob.
"""

from collections.abc import AsyncIterator
from typing import Any, Final
from urllib.parse import quote

from fastapi import APIRouter, UploadFile, status
from fastapi.responses import StreamingResponse

from agent_service.files.artifacts import CHUNK_SIZE_BYTES
from agent_service.schema.artifacts import ArtifactRef
from agent_service.service.artifacts import artifact_ref
from agent_service.service.dependencies import ArtifactServiceDep, PrincipalDep

router = APIRouter(prefix="/artifacts", tags=["artifacts"])

BINARY_MEDIA_TYPE: Final = "application/octet-stream"
# Any: bentuk bebas objek OpenAPI milik FastAPI.
DOWNLOAD_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    200: {
        "content": {BINARY_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
        "description": "File content, always as an attachment. `Content-Type` is the stored type.",
    }
}
UPLOAD_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    413: {"description": "File is larger than `ARTIFACT_MAX_BYTES`."}
}
# Karakter yang tidak aman di bagian `filename="..."` diganti, versi lengkapnya di `filename*`.
ASCII_FALLBACK_CHAR: Final = "_"
UNSAFE_QUOTED_CHARS: Final = frozenset('"\\')
FIRST_NON_ASCII_CODEPOINT: Final = 128
FIRST_PRINTABLE_CODEPOINT: Final = 32


@router.post("", status_code=status.HTTP_201_CREATED, responses=UPLOAD_RESPONSES)
async def upload_artifact(
    file: UploadFile, principal: PrincipalDep, artifacts: ArtifactServiceDep
) -> ArtifactRef:
    """Unggah satu file (multipart, field `file`). Lampirkan lewat `artifact_ids` saat chat."""
    record = await artifacts.upload(
        principal.user_id, file.filename, file.content_type, _upload_chunks(file)
    )
    return artifact_ref(record)


@router.get("/{artifact_id}", response_class=StreamingResponse, responses=DOWNLOAD_RESPONSES)
async def download_artifact(
    artifact_id: str, principal: PrincipalDep, artifacts: ArtifactServiceDep
) -> StreamingResponse:
    """Unduh isi artifact milik user. Artifact user lain → 404."""
    record = await artifacts.get(artifact_id, principal.user_id)
    content = await artifacts.open(record)
    headers = {
        "Content-Disposition": content_disposition(record.name),
        "Content-Length": str(record.size_bytes),
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox",
        "Cache-Control": "private, no-store",
    }
    return StreamingResponse(content, media_type=record.mime_type, headers=headers)


@router.delete("/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_artifact(
    artifact_id: str, principal: PrincipalDep, artifacts: ArtifactServiceDep
) -> None:
    """Hapus artifact milik user beserta isinya. Pesan yang melampirkannya tetap ada."""
    await artifacts.delete(artifact_id, principal.user_id)


def content_disposition(filename: str) -> str:
    """Header `Content-Disposition: attachment` dengan nama ASCII dan nama UTF-8 (RFC 6266).

    >>> content_disposition('laporan "Q3".pdf')
    'attachment; filename="laporan _Q3_.pdf"; filename*=UTF-8\\'\\'laporan%20%22Q3%22.pdf'
    >>> content_disposition("café.csv")
    'attachment; filename="caf_.csv"; filename*=UTF-8\\'\\'caf%C3%A9.csv'
    """
    fallback = "".join(_ascii_fallback(char) for char in filename)
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


def _ascii_fallback(char: str) -> str:
    """Karakter yang aman di dalam `filename="..."`, atau `ASCII_FALLBACK_CHAR`."""
    codepoint = ord(char)
    if codepoint < FIRST_PRINTABLE_CODEPOINT or codepoint >= FIRST_NON_ASCII_CODEPOINT:
        return ASCII_FALLBACK_CHAR
    if char in UNSAFE_QUOTED_CHARS:
        return ASCII_FALLBACK_CHAR
    return char


async def _upload_chunks(file: UploadFile) -> AsyncIterator[bytes]:
    """Baca file upload per potongan, supaya file besar tidak dimuat utuh ke memori."""
    while chunk := await file.read(CHUNK_SIZE_BYTES):
        yield chunk
