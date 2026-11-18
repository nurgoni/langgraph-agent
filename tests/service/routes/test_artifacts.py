"""Acceptance F35 (FR-46, NFR-9): upload, unduh, hapus, lampiran pesan, dan pembersihan thread."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from agent_service.core.settings import Settings
from agent_service.schema.artifacts import ArtifactRef
from agent_service.schema.responses import ChatHistory

MAX_BYTES = 1024
OTHER = "user-b"
CSV_CONTENT = b"region,total\nnorth,10\n"

type AuthHeaders = Callable[..., dict[str, str]]


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None, use_fake_model=True, database_url=database_url, artifact_max_bytes=MAX_BYTES
    )


async def upload(
    client: AsyncClient,
    content: bytes = CSV_CONTENT,
    filename: str = "sales.csv",
    mime_type: str = "text/csv",
    headers: dict[str, str] | None = None,
) -> ArtifactRef:
    response = await client.post(
        "/artifacts", files={"file": (filename, content, mime_type)}, headers=headers
    )
    assert response.status_code == 201, response.text
    return ArtifactRef.model_validate(response.json())


async def invoke(client: AsyncClient, path: str = "/invoke", **body: Any) -> str:  # Any: JSON
    response = await client.post(path, json={"message": "Look at this", **body})
    assert response.status_code == 200, response.text
    return response.headers["X-Thread-Id"]


async def history(client: AsyncClient, thread_id: str) -> ChatHistory:
    response = await client.post("/history", json={"thread_id": thread_id})
    assert response.status_code == 200, response.text
    return ChatHistory.model_validate(response.json())


def stored_files(artifact_dir: Path) -> list[str]:
    return sorted(path.name for path in artifact_dir.iterdir())


# ---------------- upload dan unduh


async def test_upload_returns_a_reference_and_download_returns_the_bytes(
    client: AsyncClient,
) -> None:
    artifact = await upload(client)

    response = await client.get(f"/artifacts/{artifact.id}")

    assert (artifact.name, artifact.mime_type, artifact.size) == ("sales.csv", "text/csv", 22)
    assert response.status_code == 200
    assert response.content == CSV_CONTENT
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-length"] == "22"
    assert response.headers["content-disposition"] == (
        "attachment; filename=\"sales.csv\"; filename*=UTF-8''sales.csv"
    )


async def test_risky_files_are_renamed_and_never_rendered_inline(client: AsyncClient) -> None:
    artifact = await upload(client, b"<script>alert(1)</script>", "../../evil.html", "text/html")

    response = await client.get(f"/artifacts/{artifact.id}")

    assert artifact.name == "evil.html"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == "sandbox"


async def test_unknown_type_is_guessed_from_the_extension(client: AsyncClient) -> None:
    artifact = await upload(client, b"{}", "data.json", "application/octet-stream")

    assert artifact.mime_type == "application/json"


async def test_file_over_the_limit_is_rejected_with_413_and_not_stored(
    client: AsyncClient, artifact_dir: Path
) -> None:
    response = await client.post(
        "/artifacts", files={"file": ("big.bin", b"x" * (MAX_BYTES + 1), "application/zip")}
    )

    assert response.status_code == 413
    assert response.json() == {"detail": f"File is larger than the limit of {MAX_BYTES} bytes"}
    assert stored_files(artifact_dir) == []


async def test_file_at_the_limit_is_accepted(client: AsyncClient) -> None:
    artifact = await upload(client, b"x" * MAX_BYTES, "exact.bin", "application/zip")

    assert artifact.size == MAX_BYTES


async def test_artifacts_require_a_token(anonymous_client: AsyncClient) -> None:
    response = await anonymous_client.post("/artifacts", files={"file": ("a.txt", b"a")})

    assert response.status_code == 401


# ---------------- isolasi dan hapus


async def test_artifact_of_another_user_is_not_found(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    artifact = await upload(client)
    other = auth_headers(OTHER)

    download = await client.get(f"/artifacts/{artifact.id}", headers=other)
    delete = await client.delete(f"/artifacts/{artifact.id}", headers=other)
    attach = await client.post(
        "/invoke", json={"message": "hi", "artifact_ids": [artifact.id]}, headers=other
    )

    assert [download.status_code, delete.status_code, attach.status_code] == [404, 404, 404]
    assert (await client.get(f"/artifacts/{artifact.id}")).status_code == 200


@pytest.mark.parametrize("artifact_id", ["not-a-uuid", "0b9e3c1e-5f7a-4c2b-9d61-3f0a2b7c8d90"])
async def test_unknown_artifact_is_not_found(client: AsyncClient, artifact_id: str) -> None:
    response = await client.get(f"/artifacts/{artifact_id}")

    assert response.status_code == 404
    assert response.json() == {"detail": f"Artifact {artifact_id!r} not found"}


async def test_deleted_artifact_is_gone_with_its_file(
    client: AsyncClient, artifact_dir: Path
) -> None:
    artifact = await upload(client)

    response = await client.delete(f"/artifacts/{artifact.id}")

    assert response.status_code == 204
    assert (await client.get(f"/artifacts/{artifact.id}")).status_code == 404
    assert stored_files(artifact_dir) == []


# ---------------- lampiran pesan


async def test_attachments_appear_on_the_human_message(client: AsyncClient) -> None:
    first, second = await upload(client), await upload(client, b"%PDF", "q3.pdf", "application/pdf")

    thread_id = await invoke(client, artifact_ids=[first.id, second.id, first.id])

    [human, _reply] = (await history(client, thread_id)).messages
    assert human.type == "human"
    assert human.artifacts == [first, second]


async def test_streamed_runs_accept_attachments(client: AsyncClient) -> None:
    artifact = await upload(client)

    response = await client.post(
        "/stream", json={"message": "Look", "artifact_ids": [artifact.id], "stream_tokens": False}
    )

    assert response.status_code == 200
    human = (await history(client, response.headers["X-Thread-Id"])).messages[0]
    assert human.artifacts == [artifact]


async def test_artifact_stays_in_the_thread_it_was_sent_to(client: AsyncClient) -> None:
    artifact = await upload(client)
    thread_id = await invoke(client, artifact_ids=[artifact.id])

    again = await client.post(
        "/invoke", json={"message": "Again", "thread_id": thread_id, "artifact_ids": [artifact.id]}
    )
    elsewhere = await client.post("/invoke", json={"message": "New", "artifact_ids": [artifact.id]})

    assert again.status_code == 200
    assert elsewhere.status_code == 409
    assert "already attached to another conversation" in elsewhere.json()["detail"]


async def test_attachments_cannot_answer_an_interrupt(client: AsyncClient) -> None:
    artifact = await upload(client)
    thread_id = await invoke(client, "/interrupt/invoke")

    answer = await client.post(
        "/interrupt/invoke",
        json={"message": "Budi", "thread_id": thread_id, "artifact_ids": [artifact.id]},
    )

    assert answer.status_code == 422
    assert answer.json()["detail"][0]["loc"] == ["body", "artifact_ids"]
    # Request yang ditolak tidak menautkan artifact, jadi masih bisa dikirim ke thread lain.
    assert await invoke(client, artifact_ids=[artifact.id])


# ---------------- pembersihan bersama thread


async def test_deleting_a_thread_deletes_its_artifacts_only(
    client: AsyncClient, artifact_dir: Path
) -> None:
    attached, unattached = await upload(client), await upload(client)
    thread_id = await invoke(client, artifact_ids=[attached.id])

    response = await client.delete(f"/threads/{thread_id}")

    assert response.status_code == 204
    assert (await client.get(f"/artifacts/{attached.id}")).status_code == 404
    assert (await client.get(f"/artifacts/{unattached.id}")).status_code == 200
    assert stored_files(artifact_dir) == [unattached.id]


async def test_deleting_a_project_deletes_artifacts_of_its_threads(client: AsyncClient) -> None:
    project = await client.post("/projects", json={"name": "Sales", "base_agent_id": "chatbot"})
    project_id = project.json()["id"]
    artifact = await upload(client)
    await invoke(client, f"/projects/{project_id}/invoke", artifact_ids=[artifact.id])

    response = await client.delete(f"/projects/{project_id}")

    assert response.status_code == 204
    assert (await client.get(f"/artifacts/{artifact.id}")).status_code == 404
