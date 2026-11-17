import uuid
from datetime import UTC, datetime, timedelta

import pytest

from agent_service.memory.database import DatabaseEngineProvider
from agent_service.memory.traces import (
    RunTraceNotFoundError,
    RunTraceRepository,
    SpanKind,
    TraceSpanRecord,
)

START = datetime(2026, 11, 17, 9, 0, tzinfo=UTC)


def span(
    run_id: str, kind: SpanKind, name: str, offset: int, owner: str = "alice"
) -> TraceSpanRecord:
    started = START + timedelta(seconds=offset)
    return TraceSpanRecord(
        span_id=run_id if kind == "run" else str(uuid.uuid4()),
        run_id=run_id,
        owner_id=owner,
        thread_id="t1",
        agent_id="chatbot",
        project_id=None,
        kind=kind,
        name=name,
        status="ok",
        started_at=started,
        ended_at=started + timedelta(seconds=1),
        duration_ms=1000,
        input_tokens=10 if kind == "model" else None,
        output_tokens=2 if kind == "model" else None,
    )


async def test_spans_are_read_back_run_first_then_by_start(database_url: str) -> None:
    run_id = str(uuid.uuid4())
    spans = [
        span(run_id, "tool", "calculator", 2),
        span(run_id, "model", "fake", 1),
        span(run_id, "run", "chatbot", 0),
    ]

    async with DatabaseEngineProvider(database_url) as engine:
        repository = RunTraceRepository(engine)
        await repository.add_spans(spans)
        stored = await repository.get_run(run_id, "alice")

    assert [(s.kind, s.name) for s in stored] == [
        ("run", "chatbot"),
        ("model", "fake"),
        ("tool", "calculator"),
    ]
    assert stored[1] == spans[1]


async def test_trace_of_another_user_or_unknown_run_is_not_found(database_url: str) -> None:
    run_id = str(uuid.uuid4())

    async with DatabaseEngineProvider(database_url) as engine:
        repository = RunTraceRepository(engine)
        await repository.add_spans([span(run_id, "run", "chatbot", 0)])
        await repository.add_spans([])
        with pytest.raises(RunTraceNotFoundError):
            await repository.get_run(run_id, "bob")
        with pytest.raises(RunTraceNotFoundError, match="not found"):
            await repository.get_run(str(uuid.uuid4()), "alice")
