from collections.abc import Iterator
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import PrivateAttr

from agent_service.core.constants import SKIP_STREAM_TAG
from agent_service.harness.context import TRUNCATION_MARKER
from agent_service.harness.context_policy import (
    ContextPolicy,
    message_units,
    messages_after,
    truncate_message,
)
from agent_service.llm.fake import FakeModel

FILLER = "lorem ipsum dolor sit amet " * 8  # ±55 token per message


class SummaryModel(FakeModel):
    """Model peringkas palsu: mencatat setiap permintaan ringkasan beserta tag run-nya."""

    _requests: list[tuple[list[BaseMessage], list[str]]] = PrivateAttr(default_factory=list)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> ChatResult:
        tags = [] if run_manager is None else list(run_manager.tags)
        self._requests.append((list(messages), tags))
        return super()._generate(messages, stop, run_manager, **kwargs)

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> Iterator[ChatGenerationChunk]:
        result = self._generate(messages, stop, run_manager, **kwargs)
        generation: ChatGeneration = result.generations[0]
        yield ChatGenerationChunk(message=generation.message)  # pyrefly: ignore[bad-argument-type]

    @property
    def requests(self) -> list[tuple[list[BaseMessage], list[str]]]:
        return self._requests


def conversation(turns: int, prefix: str = "") -> list[BaseMessage]:
    history: list[BaseMessage] = []
    for turn in range(turns):
        history.append(HumanMessage(f"{prefix}Q{turn} {FILLER}", id=f"{prefix}h{turn}"))
        history.append(AIMessage(f"{prefix}A{turn} {FILLER}", id=f"{prefix}a{turn}"))
    return history


def tool_turn(index: int, result: str = FILLER) -> list[BaseMessage]:
    call_id = f"call{index}"
    return [
        HumanMessage(f"Q{index}", id=f"h{index}"),
        AIMessage(
            "",
            id=f"a{index}",
            tool_calls=[
                {"name": "search", "args": {"q": str(index)}, "id": call_id},
                {"name": "calc", "args": {"x": str(index)}, "id": f"{call_id}b"},
            ],
        ),
        ToolMessage(result, tool_call_id=call_id, id=f"t{index}"),
        ToolMessage("42", tool_call_id=f"{call_id}b", id=f"u{index}"),
        AIMessage(f"Answer {index}", id=f"f{index}"),
    ]


def tool_pairs_intact(messages: list[BaseMessage]) -> bool:
    """Setiap tool call punya hasil, dan setiap hasil didahului tool call-nya."""
    open_calls: set[str] = set()
    for message in messages:
        if isinstance(message, AIMessage):
            if open_calls:
                return False
            open_calls = {call["id"] or "" for call in message.tool_calls}
        if isinstance(message, ToolMessage):
            if message.tool_call_id not in open_calls:
                return False
            open_calls.discard(message.tool_call_id)
    return not open_calls


def test_tool_messages_stay_with_their_call() -> None:
    units = message_units(tool_turn(1))

    assert [[type(m).__name__ for m in unit] for unit in units] == [
        ["HumanMessage"],
        ["AIMessage", "ToolMessage", "ToolMessage"],
        ["AIMessage"],
    ]


def test_messages_after_unknown_id_returns_everything() -> None:
    history = conversation(2)

    assert messages_after(history, "ghost") == history
    assert messages_after(history, "a1") == []


@pytest.mark.parametrize(("max_tokens", "keep_ratio"), [(0, 0.5), (100, 0.0), (100, 1.0)])
def test_invalid_policy_is_rejected(max_tokens: int, keep_ratio: float) -> None:
    with pytest.raises(ValueError):
        ContextPolicy(max_tokens=max_tokens, keep_ratio=keep_ratio)


async def test_history_within_budget_is_sent_as_is() -> None:
    model = SummaryModel()
    history = conversation(2)

    window = await ContextPolicy(max_tokens=1000).prepare(model, history)

    assert window.messages == history
    assert (window.summary, window.summarized_through) == ("", "")
    assert model.requests == []


async def test_older_turns_are_summarized_down_to_keep_ratio() -> None:
    model = SummaryModel(responses=["User asked Q0-Q5."])
    policy = ContextPolicy(max_tokens=500)
    history = conversation(6)

    window = await policy.prepare(model, history)

    assert window.summary == "User asked Q0-Q5."
    assert window.messages == messages_after(history, window.summarized_through)
    assert window.messages[-1].id == "a5"
    assert policy.tokens(window.messages) <= policy.max_tokens // 2
    [(prompt, tags)] = model.requests
    assert SKIP_STREAM_TAG in tags
    assert isinstance(prompt[0], SystemMessage)
    assert "Q0" in prompt[1].text
    assert window.messages[0].text not in prompt[1].text


async def test_summary_is_reused_until_the_budget_fills_again() -> None:
    model = SummaryModel(responses=["first summary", "second summary"])
    policy = ContextPolicy(max_tokens=500)
    history = conversation(6)
    first = await policy.prepare(model, history)

    history.extend(conversation(1, prefix="x"))
    second = await policy.prepare(model, history, first.summary, first.summarized_through)

    assert len(model.requests) == 1
    assert second.summary == "first summary"
    assert second.messages[-1].id == "xa0"
    assert "Current summary:\nfirst summary" not in str(model.requests[0][0])


async def test_previous_summary_is_merged_into_the_next_one() -> None:
    model = SummaryModel(responses=["first summary", "second summary", "third summary"])
    policy = ContextPolicy(max_tokens=500)
    history = conversation(6)
    first = await policy.prepare(model, history)

    history.extend(conversation(3, prefix="x"))
    second = await policy.prepare(model, history, first.summary, first.summarized_through)

    assert len(model.requests) == 2
    assert second.summary == "second summary"
    assert "Current summary:\nfirst summary" in model.requests[1][0][1].text


async def test_tool_call_pairs_are_never_split() -> None:
    policy = ContextPolicy(max_tokens=400)
    history = [message for index in range(5) for message in tool_turn(index)]

    # Model hanya dipanggil saat riwayat utuh: setelah pesan user atau setelah semua hasil tool.
    ends = [end for end in range(1, len(history) + 1) if tool_pairs_intact(history[:end])]
    for end in ends:
        window = await policy.prepare(SummaryModel(responses=["s"]), history[:end])
        assert tool_pairs_intact(window.messages)
        assert not isinstance(window.messages[0], ToolMessage)
    assert len(ends) == 3 * 5  # per giliran: pesan user, hasil tool lengkap, jawaban akhir


async def test_oversized_last_unit_is_truncated_without_touching_state() -> None:
    policy = ContextPolicy(max_tokens=1000)
    huge = "x" * 20_000
    history = tool_turn(1, result=huge)[:4]

    window = await policy.prepare(SummaryModel(responses=["s"]), history)

    assert policy.tokens(window.messages, window.summary) <= policy.max_tokens
    assert tool_pairs_intact(window.messages)
    assert [message.id for message in window.messages] == ["a1", "t1", "u1"]
    assert window.messages[1].text.endswith(TRUNCATION_MARKER)
    assert window.messages[2].text == "42"
    assert history[2].text == huge


async def test_very_long_backlog_is_summarized_in_batches() -> None:
    model = SummaryModel(responses=[f"s{index}" for index in range(1, 21)])
    policy = ContextPolicy(max_tokens=400)

    window = await policy.prepare(model, conversation(20))

    assert len(model.requests) > 1
    for prompt, _ in model.requests:
        assert count_tokens_approximately(prompt) <= policy.max_tokens + 200
    assert window.summary == f"s{len(model.requests)}"


async def test_empty_summary_keeps_the_previous_one() -> None:
    model = SummaryModel(responses=["  "])

    window = await ContextPolicy(max_tokens=500).prepare(
        model, conversation(6), summary="old summary"
    )

    assert window.summary == "old summary"


async def test_summary_is_cut_to_a_quarter_of_the_budget() -> None:
    policy = ContextPolicy(max_tokens=400)
    model = SummaryModel(responses=["y" * 5000])

    window = await policy.prepare(model, conversation(6))

    assert len(window.summary) == policy.summary_max_chars == 400


async def test_long_thread_always_fits_the_budget() -> None:
    policy = ContextPolicy(max_tokens=600)
    model = SummaryModel(responses=["summary " * 30])
    history: list[BaseMessage] = []
    summary, through = "", ""

    for index in range(15):
        history.extend(tool_turn(index) if index % 3 == 0 else conversation(1, prefix=f"{index}"))
        window = await policy.prepare(model, history, summary, through)
        summary, through = window.summary, window.summarized_through
        assert policy.tokens(window.messages, summary) <= policy.max_tokens
        assert tool_pairs_intact(window.messages)


def test_truncate_leaves_non_text_content_alone() -> None:
    message = HumanMessage(content=[{"type": "text", "text": "abc"}])

    assert truncate_message(message, 2) is message
