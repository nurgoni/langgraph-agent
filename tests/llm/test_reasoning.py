import json
from collections.abc import Iterator

import httpx
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from pydantic import SecretStr

from agent_service.core.constants import MaxTokensParam
from agent_service.llm.reasoning import (
    REASONING_KWARG,
    ReasoningChatOpenAI,
    message_reasoning,
    provider_reasoning,
)

BASE_URL = "http://llm.test/v1"


def stream_body(*deltas: dict[str, str], finish_reason: str | None = None) -> str:
    """Body SSE chat completion seperti yang dikirim Ollama.

    `finish_reason` dipasang di chunk terakhir, seperti provider menutup jawaban.
    """
    lines = []
    for index, delta in enumerate(deltas):
        is_last = index == len(deltas) - 1
        chunk = {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "qwen",
            "choices": [
                {"index": 0, "delta": delta, "finish_reason": finish_reason if is_last else None}
            ],
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


def make_model(
    body: str | dict[str, object],
    streaming: bool,
    max_tokens: int | None = None,
    requests: list[httpx.Request] | None = None,
    max_tokens_param: MaxTokensParam = "max_tokens",
) -> ReasoningChatOpenAI:
    def respond(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        if isinstance(body, str):
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(respond)
    return ReasoningChatOpenAI(
        model="qwen",
        base_url=BASE_URL,
        api_key=SecretStr("sk-test"),
        streaming=streaming,
        max_tokens=max_tokens,
        max_tokens_param=max_tokens_param,
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


@pytest.mark.parametrize(
    ("param", "absent"),
    [("max_tokens", "max_completion_tokens"), ("max_completion_tokens", "max_tokens")],
)
def test_max_tokens_is_sent_under_configured_name(param: MaxTokensParam, absent: str) -> None:
    requests: list[httpx.Request] = []
    model = make_model(
        OLLAMA_STREAM, streaming=True, max_tokens=64, requests=requests, max_tokens_param=param
    )

    model.invoke("warna")

    [request] = requests
    body = json.loads(request.content)
    assert body[param] == 64
    assert absent not in body


def test_no_limit_sends_no_token_field() -> None:
    requests: list[httpx.Request] = []

    make_model(OLLAMA_STREAM, streaming=True, requests=requests).invoke("warna")

    body = json.loads(requests[0].content)
    assert "max_tokens" not in body
    assert "max_completion_tokens" not in body


def test_length_finish_reason_reaches_response_metadata() -> None:
    body = stream_body({"content": "", "reasoning": "Hmm"}, finish_reason="length")

    message = make_model(body, streaming=True, max_tokens=1).invoke("warna")

    assert message.response_metadata["finish_reason"] == "length"
