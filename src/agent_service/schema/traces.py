"""Model response trace run agent (FR-41).

Trace hanya berisi nama, waktu, status, dan token. Isi prompt, jawaban, dan hasil tool tidak
disimpan.

>>> from datetime import datetime, timezone
>>> now = datetime(2026, 11, 17, tzinfo=timezone.utc)
>>> span = TraceSpan(kind="model", name="qwen3.5:9b", status="ok", started_at=now,
...                  ended_at=now, duration_ms=1200, input_tokens=50, output_tokens=8)
>>> span.duration_ms
1200
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

type TraceSpanKind = Literal["model", "tool"]
type TraceStatus = Literal["ok", "error", "interrupted"]


class TraceSpan(BaseModel):
    """Satu panggilan model atau tool di dalam run."""

    kind: TraceSpanKind
    name: str = Field(description="Model name, or tool name such as `load_skill`.")
    status: TraceStatus
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    input_tokens: int | None = Field(
        default=None, description="Prompt tokens, if the model provider reported usage."
    )
    output_tokens: int | None = None
    error: str | None = Field(default=None, description="Exception type and message.")


class RunTrace(BaseModel):
    """Isi `GET /runs/{run_id}/trace`: ringkasan run dan span-nya, urut waktu mulai."""

    run_id: str
    thread_id: str
    agent_id: str
    project_id: str | None
    status: TraceStatus = Field(
        description="`interrupted` means the run stopped to ask the user (FR-12)."
    )
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    input_tokens: int | None = Field(default=None, description="Sum over all model calls.")
    output_tokens: int | None = None
    error: str | None = None
    spans: list[TraceSpan]
