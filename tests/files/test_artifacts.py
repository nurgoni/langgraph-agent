from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from agent_service.files.artifacts import (
    ArtifactContentMissingError,
    ArtifactTooLargeError,
    InvalidStorageKeyError,
    LocalArtifactStore,
)

KEY = "0b9e3c1e-5f7a-4c2b-9d61-3f0a2b7c8d90"


async def chunks_of(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


async def read_all(store: LocalArtifactStore, key: str) -> bytes:
    content = b""
    async for chunk in await store.open(key):
        content += chunk
    return content


@pytest.fixture
async def store(tmp_path: Path) -> LocalArtifactStore:
    artifact_store = LocalArtifactStore(tmp_path / "nested" / "artifacts")
    await artifact_store.prepare()
    return artifact_store


async def test_written_content_is_read_back(store: LocalArtifactStore) -> None:
    size = await store.write(KEY, chunks_of(b"hello ", b"world"), max_bytes=11)

    assert size == 11
    assert await read_all(store, KEY) == b"hello world"


async def test_content_over_the_limit_is_rejected_without_leaving_files(
    store: LocalArtifactStore, tmp_path: Path
) -> None:
    with pytest.raises(ArtifactTooLargeError) as error:
        await store.write(KEY, chunks_of(b"12345", b"6"), max_bytes=5)

    assert error.value.max_bytes == 5
    assert list((tmp_path / "nested" / "artifacts").iterdir()) == []


@pytest.mark.parametrize("key", ["../escape", "a/b", "", ".hidden", "x" * 200])
async def test_keys_that_could_leave_the_directory_are_rejected(
    store: LocalArtifactStore, key: str
) -> None:
    with pytest.raises(InvalidStorageKeyError):
        await store.write(key, chunks_of(b"x"), max_bytes=10)


async def test_missing_content_and_repeated_delete(store: LocalArtifactStore) -> None:
    await store.write(KEY, chunks_of(b"x"), max_bytes=10)
    await store.delete(KEY)
    await store.delete(KEY)

    with pytest.raises(ArtifactContentMissingError):
        await store.open(KEY)
