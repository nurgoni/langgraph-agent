import json
from collections.abc import Iterator

import httpx
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from pydantic import SecretStr

from agent_service.llm.reasoning import (
    REASONING_KWARG,
    ReasoningChatOpenAI,
    message_reasoning,
    provider_reasoning,
)

BASE_URL = "http://llm.test/v1"


def stream_body(*deltas: dict[str, str]) -> str:
    """Body SSE chat completion seperti yang dikirim Ollama."""
    lines = []
    for delta in deltas:
        chunk = {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "qwen",
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
        }
        lines.append(f"data: {json.dumps(chunk)}\n\n")
    return "".join(lines) + "data: [DONE]\n\n"


def completion_body(message: dict[str, str]) -> dict[str, object]:
    return {
        "id": "c1",
        "object": "chat.completion",
        "created": 0,
        "model": "qwen",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
    }


def make_model(body: str | dict[str, object], streaming: bool) -> ReasoningChatOpenAI:
    def respond(request: httpx.Request) -> httpx.Response:
        if isinstance(body, str):
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(respond)
    return ReasoningChatOpenAI(
        model="qwen",
        base_url=BASE_URL,
        api_key=SecretStr("sk-test"),
        streaming=streaming,
        http_client=httpx.Client(transport=transport),
        http_async_client=httpx.AsyncClient(transport=transport),
    )


OLLAMA_STREAM = stream_body(
    {"role": "assistant", "content": "", "reasoning": "Pilih "},
    {"content": "", "reasoning": "tiga warna."},
    {"content": "Merah, "},
    {"content": "biru."},
)


def test_stream_chunks_carry_reasoning_then_content() -> None:
    chunks = list(make_model(OLLAMA_STREAM, streaming=True).stream("warna"))

    reasoning = [c.additional_kwargs.get(REASONING_KWARG, "") for c in chunks]
    assert "".join(reasoning) == "Pilih tiga warna."
    assert "".join(str(c.content) for c in chunks) == "Merah, biru."


def test_streamed_invoke_merges_reasoning_into_final_message() -> None:
    message = make_model(OLLAMA_STREAM, streaming=True).invoke("warna")

    assert isinstance(message, AIMessage)
    assert message.content == "Merah, biru."
    assert message_reasoning(message) == "Pilih tiga warna."


async def test_async_stream_carries_reasoning() -> None:
    model = make_model(OLLAMA_STREAM, streaming=True)

    merged: AIMessageChunk | None = None
    async for chunk in model.astream("warna"):
        merged = chunk if merged is None else merged + chunk

    assert merged is not None
    assert merged.additional_kwargs[REASONING_KWARG] == "Pilih tiga warna."


@pytest.mark.parametrize("field", ["reasoning", "reasoning_content"])
def test_non_stream_response_keeps_reasoning(field: str) -> None:
    body = completion_body({"role": "assistant", "content": "Merah.", field: "Satu warna."})

    message = make_model(body, streaming=False).invoke("warna")

    assert isinstance(message, AIMessage)
    assert message_reasoning(message) == "Satu warna."


def test_model_without_reasoning_is_unchanged() -> None:
    body = stream_body({"role": "assistant", "content": "Halo"})

    message = make_model(body, streaming=True).invoke("hai")

    assert REASONING_KWARG not in message.additional_kwargs


def test_provider_reasoning_prefers_first_known_field() -> None:
    assert provider_reasoning({"reasoning": "a", "reasoning_content": "b"}) == "a"
    assert provider_reasoning({"reasoning": "", "reasoning_content": "b"}) == "b"
    assert provider_reasoning({"reasoning": None}) == ""


def test_message_reasoning_ignores_non_string() -> None:
    message = AIMessage(content="x", additional_kwargs={REASONING_KWARG: ["not", "text"]})

    assert message_reasoning(message) == ""


@pytest.fixture(autouse=True)
def _no_env_keys(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    yield
