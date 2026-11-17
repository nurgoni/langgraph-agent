"""Endpoint `/runs/{run_id}/trace`: trace satu run milik user (FR-41, keputusan user F31).

`run_id` ada di setiap `ChatMessage` hasil run. Trace milik user lain dijawab 404, sama seperti
run yang tidak ada (NFR-9).
"""

from uuid import UUID

from fastapi import APIRouter

from agent_service.memory.traces import TraceSpanRecord
from agent_service.schema.traces import RunTrace, TraceSpan
from agent_service.service.dependencies import PrincipalDep, TraceRepositoryDep

router = APIRouter(prefix="/runs", tags=["runs"])


def trace_span(record: TraceSpanRecord) -> TraceSpan:
    """Span repository (`model`/`tool`) menjadi schema API."""
    return TraceSpan(
        kind="tool" if record.kind == "tool" else "model",
        name=record.name,
        status=record.status,
        started_at=record.started_at,
        ended_at=record.ended_at,
        duration_ms=record.duration_ms,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
        error=record.error,
    )


def run_trace(records: list[TraceSpanRecord]) -> RunTrace:
    """Gabungkan span `run` (record pertama) dan span lain menjadi `RunTrace`."""
    run, *spans = records
    return RunTrace(
        run_id=run.run_id,
        thread_id=run.thread_id,
        agent_id=run.agent_id,
        project_id=run.project_id,
        status=run.status,
        started_at=run.started_at,
        ended_at=run.ended_at,
        duration_ms=run.duration_ms,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        error=run.error,
        spans=[trace_span(span) for span in spans],
    )


@router.get("/{run_id}/trace")
async def get_run_trace(
    run_id: UUID, principal: PrincipalDep, traces: TraceRepositoryDep
) -> RunTrace:
    """Trace satu run: durasi, token, dan setiap panggilan model/tool. Run user lain → 404."""
    records = await traces.get_run(str(run_id), principal.user_id)
    return run_trace(records)
