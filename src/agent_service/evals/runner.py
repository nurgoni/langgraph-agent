"""Runner eval: menjalankan setiap kasus lewat `AgentClient`, sama seperti user (FR-41).

Per kasus: kirim pesan ke thread baru, ambil riwayat thread (tool call dan skill yang dimuat),
ambil trace run (latensi dan token), lalu skor. Kegagalan HTTP pada satu kasus dicatat sebagai
kasus gagal, dan kasus berikutnya tetap dijalankan.
"""

import logging
import time
from collections.abc import Callable

from agent_service.client import AgentClient, AgentClientError
from agent_service.evals.dataset import EvalCase, EvalDataset
from agent_service.evals.report import CaseResult, DatasetReport, excerpt
from agent_service.evals.scoring import observe, score_case
from agent_service.schema.traces import RunTrace

logger = logging.getLogger(__name__)

type Timer = Callable[[], float]


class EvalRunner:
    """Menjalankan dataset terhadap satu service lewat client yang sudah login."""

    def __init__(
        self, client: AgentClient, model: str | None = None, timer: Timer = time.perf_counter
    ) -> None:
        """Inisialisasi runner.

        Args:
            client: Client yang sudah memegang access token (service account).
            model: Model untuk semua kasus. `None` berarti model project atau default service.
            timer: Sumber waktu untuk latensi cadangan (jika trace tidak tersedia).
        """
        self._client = client
        self._model = model
        self._timer = timer

    async def run(self, dataset: EvalDataset) -> DatasetReport:
        """Jalankan semua kasus secara berurutan, supaya latensi tidak saling memengaruhi."""
        results: list[CaseResult] = []
        for case in dataset.cases:
            result = await self._run_case(dataset, case)
            logger.info("%s/%s: %s", dataset.name, case.id, "pass" if result.passed else "FAIL")
            results.append(result)
        return DatasetReport(name=dataset.name, model=self._model, cases=results)

    async def _run_case(self, dataset: EvalDataset, case: EvalCase) -> CaseResult:
        """Satu kasus di thread baru. Error HTTP menjadi kasus gagal dengan pesan error."""
        self._client.agent_id, self._client.project_id = dataset.target_for(case)
        started = self._timer()
        try:
            reply = await self._client.ainvoke(case.input, model=self._model)
            wall_seconds = self._timer() - started
            history = await self._client.aget_history(reply.thread_id)
            trace = await self._trace(reply.message.run_id)
        except AgentClientError as error:
            return CaseResult(case_id=case.id, passed=False, checks=[], error=str(error))
        observation = observe(reply.message, history.messages, trace, wall_seconds)
        checks = score_case(case.expect, observation)
        return CaseResult(
            case_id=case.id,
            passed=all(check.passed for check in checks),
            checks=checks,
            reply=excerpt(observation.reply),
            run_id=reply.message.run_id,
            latency_seconds=observation.latency_seconds,
            input_tokens=observation.input_tokens,
            output_tokens=observation.output_tokens,
        )

    async def _trace(self, run_id: str | None) -> RunTrace | None:
        """Trace run, atau `None` jika run tidak punya trace (misalnya penyimpanan trace gagal)."""
        if run_id is None:
            return None
        try:
            return await self._client.aget_run_trace(run_id)
        except AgentClientError as error:
            logger.warning("No trace for run %s: %s", run_id, error)
            return None
