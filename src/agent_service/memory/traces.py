"""Penyimpanan trace run agent di tabel Postgres `run_traces` (FR-41, keputusan user F31).

Repository tidak mengenal LangChain: span dikumpulkan oleh callback di `service/tracing.py`, lalu
ditulis sekaligus di akhir run. Pembacaan selalu disaring pemilik run, jadi trace milik user lain
tidak bisa dibaca (NFR-9).
"""

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Final, Literal

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_service.memory.tables import run_traces_table

type SpanKind = Literal["run", "model", "tool"]
type SpanStatus = Literal["ok", "error", "interrupted"]

RUN_SPAN_KIND: Final = "run"


class RunTraceNotFoundError(LookupError):
    """Run tidak punya trace, atau trace-nya milik user lain."""

    def __init__(self, run_id: str) -> None:
        """Inisialisasi error dengan pesan yang tidak membocorkan pemilik run."""
        super().__init__(f"Trace for run {run_id!r} not found")


@dataclass(frozen=True)
class TraceSpanRecord:
    """Satu span trace: seluruh run, satu panggilan model, atau satu panggilan tool."""

    span_id: str
    run_id: str
    owner_id: str
    thread_id: str
    agent_id: str
    project_id: str | None
    kind: SpanKind
    name: str
    status: SpanStatus
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None


class RunTraceRepository:
    """Menulis dan membaca span trace.

    Engine dibuat dan ditutup oleh `DatabaseEngineProvider` di lifespan.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        """Inisialisasi repository.

        Args:
            engine: Engine ke database yang sudah dimigrasi.
        """
        self._engine = engine

    async def add_spans(self, spans: Sequence[TraceSpanRecord]) -> None:
        """Simpan semua span satu run dalam satu transaksi. Daftar kosong tidak ditulis."""
        if not spans:
            return
        rows = [asdict(span) for span in spans]
        async with self._engine.begin() as connection:
            await connection.execute(insert(run_traces_table), rows)

    async def get_run(self, run_id: str, owner_id: str) -> list[TraceSpanRecord]:
        """Semua span satu run milik `owner_id`, span `run` lebih dulu, lalu urut waktu mulai.

        Raises:
            RunTraceNotFoundError: Jika run tidak punya trace atau milik user lain.
        """
        table = run_traces_table
        query = (
            select(table)
            .where(table.c.run_id == run_id, table.c.owner_id == owner_id)
            .order_by((table.c.kind != RUN_SPAN_KIND), table.c.started_at)
        )
        async with self._engine.connect() as connection:
            result = await connection.execute(query)
            spans = [TraceSpanRecord(**row._asdict()) for row in result]
        if not spans or spans[0].kind != RUN_SPAN_KIND:
            raise RunTraceNotFoundError(run_id)
        return spans


if __name__ == "__main__":
    import asyncio
    import uuid
    from datetime import UTC

    from agent_service.core.constants import DEFAULT_DATABASE_URL
    from agent_service.memory.database import DatabaseEngineProvider

    async def _demo() -> None:
        # Butuh `docker compose up -d postgres` dan `uv run python -m agent_service.run_migrate`.
        run_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        span = TraceSpanRecord(
            run_id, run_id, "demo", "t1", "chatbot", None, "run", "chatbot", "ok", now, now, 0
        )
        async with DatabaseEngineProvider(DEFAULT_DATABASE_URL) as engine:
            repository = RunTraceRepository(engine)
            await repository.add_spans([span])
            print(await repository.get_run(run_id, "demo"))

    asyncio.run(_demo())
