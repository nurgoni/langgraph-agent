import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from langchain_core.messages import AIMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphInterrupt
from sqlalchemy.exc import OperationalError

from agent_service.memory.traces import RunTraceRepository, TraceSpanRecord
from agent_service.service.run_input import RunInput
from agent_service.service.tracing import RunTraceCollector, token_usage

START = datetime(2026, 11, 17, 9, 0, tzinfo=UTC)
RUN_ID = uuid.uuid4()


class FakeRepository(RunTraceRepository):
    """Repository tanpa database: menyimpan span di memori, atau gagal seperti database mati."""

    def __init__(self, fail: bool = False) -> None:
        self.saved: list[TraceSpanRecord] = []
        self._fail = fail

    async def add_spans(self, spans: Sequence[TraceSpanRecord]) -> None:
        if self._fail:
            raise OperationalError("INSERT", {}, Exception("database is down"))
        self.saved.extend(spans)


class StepClock:
    """Jam tiruan yang maju satu detik setiap kali dibaca."""

    def __init__(self) -> None:
        self._ticks = 0

    def __call__(self) -> datetime:
        moment = START + timedelta(seconds=self._ticks)
        self._ticks += 1
        return moment


def run_input() -> RunInput:
    return RunInput(
        graph_input={},
        config=RunnableConfig(configurable={"thread_id": "t1", "user_id": "alice"}),
        run_id=RUN_ID,
        thread_id="t1",
        user_id="alice",
    )


def collector(repository: RunTraceRepository | None = None) -> RunTraceCollector:
    return RunTraceCollector(
        repository or FakeRepository(), run_input(), "chatbot", "p1", clock=StepClock()
    )


def llm_result(input_tokens: int, output_tokens: int) -> LLMResult:
    usage = UsageMetadata(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )
    message = AIMessage("hi", usage_metadata=usage)
    return LLMResult(generations=[[ChatGeneration(message=message)]])


async def test_model_and_tool_spans_are_recorded_with_token_totals() -> None:
    tracer = collector()
    first, tool, second = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    await tracer.on_chat_model_start({}, [], run_id=first, metadata={"ls_model_name": "qwen"})
    await tracer.on_llm_end(llm_result(100, 5), run_id=first)
    await tracer.on_tool_start({"name": "calculator"}, "1+1", run_id=tool)
    await tracer.on_tool_end("2", run_id=tool)
    await tracer.on_chat_model_start({}, [], run_id=second, name="FakeModel")
    await tracer.on_llm_end(llm_result(120, 7), run_id=second)
    spans = tracer.finish("ok")

    run, *calls = spans
    assert (run.kind, run.name, run.status, run.span_id) == ("run", "chatbot", "ok", str(RUN_ID))
    assert (run.input_tokens, run.output_tokens) == (220, 12)
    assert (run.owner_id, run.thread_id, run.project_id) == ("alice", "t1", "p1")
    assert [(s.kind, s.name, s.duration_ms) for s in calls] == [
        ("model", "qwen", 1000),
        ("tool", "calculator", 1000),
        ("model", "FakeModel", 1000),
    ]
    assert run.duration_ms == 7000


async def test_failed_and_interrupted_calls_get_their_status() -> None:
    tracer = collector()
    model, tool = uuid.uuid4(), uuid.uuid4()

    await tracer.on_chat_model_start({}, [], run_id=model)
    await tracer.on_llm_error(TimeoutError("model timed out"), run_id=model)
    await tracer.on_tool_start({"name": "save_memory"}, "{}", run_id=tool)
    await tracer.on_tool_error(GraphInterrupt(), run_id=tool)
    run, failed, interrupted = tracer.finish("interrupted")

    assert (failed.status, failed.error) == ("error", "TimeoutError: model timed out")
    assert (failed.input_tokens, run.input_tokens) == (None, None)
    assert (interrupted.name, interrupted.status) == ("save_memory", "interrupted")
    assert run.status == "interrupted"


async def test_unfinished_spans_take_the_run_status_and_unknown_ids_are_ignored() -> None:
    tracer = collector()
    await tracer.on_tool_start({"name": "web_search"}, "q", run_id=uuid.uuid4())
    await tracer.on_tool_end("late", run_id=uuid.uuid4())

    run, unfinished = tracer.finish("error", "CancelledError: client went away")

    assert (unfinished.name, unfinished.status) == ("web_search", "error")
    assert run.error == "CancelledError: client went away"


async def test_save_writes_all_spans_and_survives_a_database_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = FakeRepository()
    tracer = collector(repository)
    await tracer.on_tool_start({"name": "calculator"}, "1", run_id=uuid.uuid4())

    await tracer.save("error", ValueError("boom"))
    await collector(FakeRepository(fail=True)).save("ok")

    assert [s.kind for s in repository.saved] == ["run", "tool"]
    assert repository.saved[0].error == "ValueError: boom"
    assert "Failed to save trace" in caplog.text


def test_token_usage_is_unknown_without_usage_metadata() -> None:
    plain = LLMResult(generations=[[ChatGeneration(message=AIMessage("hi"))]])

    assert token_usage(plain) == (None, None)
    assert token_usage(LLMResult(generations=[])) == (None, None)
