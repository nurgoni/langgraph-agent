"""Chat model palsu untuk test dan mode `USE_FAKE_MODEL`, tanpa network call."""

import json
import re
from collections.abc import Callable, Iterator, Sequence
from typing import Any, Final

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import Field, PrivateAttr, field_validator

from agent_service.llm.reasoning import REASONING_KWARG, message_reasoning

DEFAULT_FAKE_RESPONSE: Final = "This is a response from the fake model."
FAKE_LLM_TYPE: Final = "agent-service-fake"
# Satu token = satu kata beserta whitespace sesudahnya, supaya gabungan token sama persis
# dengan teks asli.
TOKEN_PATTERN: Final = re.compile(r"\S+\s*|\s+")


def _default_responses() -> list[AIMessage]:
    """Respons bawaan: satu jawaban teks tetap."""
    return [AIMessage(content=DEFAULT_FAKE_RESPONSE)]


class FakeModel(BaseChatModel):
    """Chat model yang membalas dengan daftar respons yang sudah ditentukan, berurutan.

    Setelah respons terakhir, urutan kembali ke awal. Respons boleh berisi `tool_calls`
    untuk menguji agent yang memanggil tool. `tool_calls` tetap utuh saat streaming. Reasoning
    di `additional_kwargs[REASONING_KWARG]` di-stream lebih dulu, seperti model reasoning.

    >>> model = FakeModel(responses=["Halo dunia"])
    >>> model.invoke("hi").content
    'Halo dunia'
    >>> [chunk.content for chunk in model.stream("hi") if chunk.content]
    ['Halo ', 'dunia']
    """

    responses: list[AIMessage] = Field(default_factory=_default_responses, min_length=1)
    _next_index: int = PrivateAttr(default=0)

    @field_validator("responses", mode="before")
    @classmethod
    def _wrap_text_responses(cls, value: object) -> object:
        """Ubah string menjadi `AIMessage` agar script respons bisa ditulis ringkas.

        Args:
            value: Nilai mentah field `responses`.

        Returns:
            List dengan setiap string diganti `AIMessage`, atau `value` apa adanya jika
            bukan list.
        """
        if not isinstance(value, list):
            return value
        messages: list[object] = []
        for item in value:
            if isinstance(item, str):
                messages.append(AIMessage(content=item))
            else:
                messages.append(item)
        return messages

    @property
    def _llm_type(self) -> str:
        """Identitas model untuk callback dan tracing LangChain."""
        return FAKE_LLM_TYPE

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],  # Any: API induk
        *,
        tool_choice: str | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> Runnable[LanguageModelInput, AIMessage]:
        """Abaikan tools, karena tool call sudah ditentukan di `responses`.

        Returns:
            Instance yang sama.
        """
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> ChatResult:
        """Kembalikan respons berikutnya secara utuh."""
        return ChatResult(generations=[ChatGeneration(message=self._next_response())])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> Iterator[ChatGenerationChunk]:
        """Pecah respons berikutnya: reasoning per kata, token teks, lalu chunk tool call."""
        response = self._next_response()
        yield from self._reasoning_chunks(response, run_manager)
        for token in TOKEN_PATTERN.findall(response.text):
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=token, id=response.id))
            if run_manager is not None:
                run_manager.on_llm_new_token(token, chunk=chunk)
            yield chunk
        if response.tool_calls:
            yield ChatGenerationChunk(message=self._tool_call_chunk(response))

    @staticmethod
    def _reasoning_chunks(
        response: AIMessage, run_manager: CallbackManagerForLLMRun | None
    ) -> Iterator[ChatGenerationChunk]:
        """Reasoning di `additional_kwargs` di-stream per kata, seperti model reasoning asli."""
        for piece in TOKEN_PATTERN.findall(message_reasoning(response)):
            message = AIMessageChunk(
                content="", id=response.id, additional_kwargs={REASONING_KWARG: piece}
            )
            chunk = ChatGenerationChunk(message=message)
            if run_manager is not None:
                run_manager.on_llm_new_token("", chunk=chunk)
            yield chunk

    def _next_response(self) -> AIMessage:
        """Ambil salinan respons pada giliran ini, lalu majukan indeks secara melingkar.

        Salinan dibutuhkan karena reducer `add_messages` LangGraph mengisi `id` message secara
        in-place. Tanpa salinan, respons yang berulang punya `id` sama dan menimpa jawaban lama
        di riwayat thread.
        """
        response = self.responses[self._next_index]
        self._next_index = (self._next_index + 1) % len(self.responses)
        return response.model_copy(deep=True)

    @staticmethod
    def _tool_call_chunk(response: AIMessage) -> AIMessageChunk:
        """Bungkus semua `tool_calls` milik respons dalam satu `AIMessageChunk`."""
        chunks = []
        for index, tool_call in enumerate(response.tool_calls):
            chunks.append(
                tool_call_chunk(
                    name=tool_call["name"],
                    args=json.dumps(tool_call["args"]),
                    id=tool_call["id"],
                    index=index,
                )
            )
        return AIMessageChunk(content="", id=response.id, tool_call_chunks=chunks)


if __name__ == "__main__":
    scripted = FakeModel(
        responses=[
            AIMessage(content="", tool_calls=[{"name": "add", "args": {"a": 1}, "id": "call-1"}]),
            "Hasilnya 1.",
        ]
    )
    print(scripted.invoke("tambah").tool_calls)
    print(scripted.invoke("lanjut").content)
