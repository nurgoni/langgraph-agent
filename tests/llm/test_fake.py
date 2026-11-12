import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.messages.tool import tool_call
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError

from agent_service.agents.chatbot import ChatbotAgent
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


def test_each_call_returns_a_fresh_message() -> None:
    model = FakeModel(responses=["sama"])

    first, second = model.invoke("a"), model.invoke("b")

    assert first is not second
    assert first is not model.responses[0]


async def test_repeated_response_is_appended_to_thread_history() -> None:
    graph = ChatbotAgent().build(FakeModel(responses=["sama"]), InMemorySaver())
    config: RunnableConfig = {"configurable": {"thread_id": "t1"}}

    await graph.ainvoke({"messages": [HumanMessage("a")]}, config)
    result = await graph.ainvoke({"messages": [HumanMessage("b")]}, config)

    assert [m.content for m in result["messages"]] == ["a", "sama", "b", "sama"]


REASONED = AIMessage(
    content="Merah, biru", additional_kwargs={"reasoning_content": "Pilih tiga warna"}
)


def test_stream_sends_reasoning_before_answer_tokens() -> None:
    chunks = list(FakeModel(responses=[REASONED]).stream("warna"))

    reasoning = [c.additional_kwargs.get("reasoning_content", "") for c in chunks]
    contents = [c.content for c in chunks]
    first_answer = next(i for i, content in enumerate(contents) if content)
    assert "".join(reasoning) == "Pilih tiga warna"
    assert all(not text for text in reasoning[first_answer:])
    assert "".join(str(content) for content in contents) == "Merah, biru"


def test_merged_stream_keeps_full_reasoning() -> None:
    merged: AIMessageChunk | None = None
    for chunk in FakeModel(responses=[REASONED]).stream("warna"):
        merged = chunk if merged is None else merged + chunk

    assert merged is not None
    assert merged.additional_kwargs["reasoning_content"] == "Pilih tiga warna"


def test_invoke_returns_reasoning_untouched() -> None:
    message = FakeModel(responses=[REASONED]).invoke("warna")

    assert message.additional_kwargs == {"reasoning_content": "Pilih tiga warna"}
