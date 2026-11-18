import uuid

from agent_service.memory.artifacts import ArtifactRepository, NewArtifact
from agent_service.memory.database import DatabaseEngineProvider


def new_artifact(owner: str = "alice", thread_id: str | None = None) -> NewArtifact:
    artifact_id = str(uuid.uuid4())
    return NewArtifact(
        artifact_id=artifact_id,
        owner_id=owner,
        name="sales.csv",
        mime_type="text/csv",
        size_bytes=12,
        storage_key=artifact_id,
        thread_id=thread_id,
    )


async def test_artifacts_are_read_only_by_their_owner(database_url: str) -> None:
    mine, theirs = new_artifact("alice"), new_artifact("bob")

    async with DatabaseEngineProvider(database_url) as engine:
        repository = ArtifactRepository(engine)
        stored = await repository.add(mine)
        await repository.add(theirs)
        found = await repository.get_owned(
            [mine.artifact_id, theirs.artifact_id, "not-a-uuid"], "alice"
        )

    assert [record.artifact_id for record in found] == [mine.artifact_id]
    assert (stored.name, stored.size_bytes, stored.thread_id) == ("sales.csv", 12, None)
    assert stored.created_at is not None


async def test_linking_only_claims_unattached_artifacts(database_url: str) -> None:
    unattached, attached = new_artifact(), new_artifact(thread_id="t-old")

    async with DatabaseEngineProvider(database_url) as engine:
        repository = ArtifactRepository(engine)
        await repository.add(unattached)
        await repository.add(attached)
        await repository.link_to_thread([unattached.artifact_id, attached.artifact_id], "t-new")
        found = await repository.get_owned([unattached.artifact_id, attached.artifact_id], "alice")

    threads = {record.artifact_id: record.thread_id for record in found}
    assert threads == {unattached.artifact_id: "t-new", attached.artifact_id: "t-old"}


async def test_deleting_a_thread_returns_its_artifacts(database_url: str) -> None:
    in_thread, elsewhere = new_artifact(thread_id="t1"), new_artifact(thread_id="t2")

    async with DatabaseEngineProvider(database_url) as engine:
        repository = ArtifactRepository(engine)
        await repository.add(in_thread)
        await repository.add(elsewhere)
        deleted = await repository.delete_thread("t1")
        remaining = await repository.get_owned(
            [in_thread.artifact_id, elsewhere.artifact_id], "alice"
        )

    assert [record.storage_key for record in deleted] == [in_thread.storage_key]
    assert [record.artifact_id for record in remaining] == [elsewhere.artifact_id]
