import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.messages.tool import tool_call
from langchain_core.tools import tool
from pydantic import ValidationError

from agent_service.llm.fake import DEFAULT_FAKE_RESPONSE, FakeModel

ADD_CALL = tool_call(name="add", args={"a": 1, "b": 2}, id="call-1")


@tool
def add(a: int, b: int) -> int:
    """Jumlahkan dua bilangan."""
    return a + b


def test_default_response_is_fixed_text() -> None:
    assert FakeModel().invoke("hi").content == DEFAULT_FAKE_RESPONSE


def test_responses_cycle_in_order() -> None:
    model = FakeModel(responses=["first", "second"])

    contents = [model.invoke("hi").content for _ in range(3)]

    assert contents == ["first", "second", "first"]


def test_empty_responses_are_rejected() -> None:
    with pytest.raises(ValidationError):
        FakeModel(responses=[])


def test_bind_tools_returns_same_model() -> None:
    model = FakeModel()

    assert model.bind_tools([add]) is model


def test_invoke_returns_scripted_tool_call() -> None:
    model = FakeModel(responses=[AIMessage(content="", tool_calls=[ADD_CALL])])

    message = model.invoke("hitung")

    assert isinstance(message, AIMessage)
    assert message.tool_calls == [ADD_CALL]


def test_stream_yields_word_tokens_that_join_to_original_text() -> None:
    model = FakeModel(responses=["Halo  dunia ini"])

    # BaseChatModel selalu menutup stream dengan chunk kosong penanda akhir.
    tokens = [chunk.content for chunk in model.stream("hi") if chunk.content]

    assert tokens == ["Halo  ", "dunia ", "ini"]
    assert "".join(str(token) for token in tokens) == "Halo  dunia ini"


def test_stream_keeps_tool_calls_when_chunks_are_merged() -> None:
    model = FakeModel(responses=[AIMessage(content="Sebentar", tool_calls=[ADD_CALL])])

    merged: AIMessageChunk | None = None
    for chunk in model.stream("hitung"):
        merged = chunk if merged is None else merged + chunk

    assert merged is not None
    assert merged.content == "Sebentar"
    assert merged.tool_calls == [ADD_CALL]


async def test_astream_yields_same_tokens_as_stream() -> None:
    model = FakeModel(responses=["satu dua"])

    tokens = [chunk.content async for chunk in model.astream("hi") if chunk.content]

    assert tokens == ["satu ", "dua"]
