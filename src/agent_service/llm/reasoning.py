"""Chat model OpenAI-compatible yang mempertahankan reasoning model (FR-29).

Model reasoning (misalnya Qwen3 lewat Ollama) mengirim pemikirannya di field non-standar
(`reasoning` atau `reasoning_content`), di luar `content`. `ChatOpenAI` membuang field itu, jadi
subclass ini menyalinnya ke `additional_kwargs[REASONING_KWARG]`. Saat streaming, LangChain
menggabungkan string per chunk sehingga message akhir berisi reasoning lengkap.
"""

from collections.abc import Mapping
from typing import Any, Final

import openai
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI

REASONING_KWARG: Final = "reasoning_content"
# Nama field reasoning yang dipakai provider OpenAI-compatible: Ollama mengirim `reasoning`,
# vLLM dan DeepSeek mengirim `reasoning_content`.
PROVIDER_REASONING_FIELDS: Final = ("reasoning", "reasoning_content")
CHOICES_KEY: Final = "choices"


def provider_reasoning(fields: Mapping[str, object]) -> str:
    """Ambil teks reasoning dari `delta` (stream) atau `message` (non-stream) milik provider.

    >>> provider_reasoning({"content": "", "reasoning": "Pertama, "})
    'Pertama, '
    >>> provider_reasoning({"content": "Halo"})
    ''
    """
    for field in PROVIDER_REASONING_FIELDS:
        value = fields.get(field)
        if isinstance(value, str) and value:
            return value
    return ""


def message_reasoning(message: AIMessage) -> str:
    """Reasoning yang tersimpan di message AI, atau string kosong.

    >>> message_reasoning(AIMessage(content="Hai", additional_kwargs={REASONING_KWARG: "Hmm"}))
    'Hmm'
    """
    value = message.additional_kwargs.get(REASONING_KWARG)
    return value if isinstance(value, str) else ""


class ReasoningChatOpenAI(ChatOpenAI):
    """`ChatOpenAI` yang menyimpan reasoning provider di `additional_kwargs[REASONING_KWARG]`.

    Class karena memperluas model LangChain. Perilaku lain sama persis dengan `ChatOpenAI`, jadi
    model tanpa reasoning tidak terpengaruh.
    """

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict[str, Any],  # Any: chunk JSON mentah dari provider
        default_chunk_class: type,
        base_generation_info: dict[str, Any] | None,  # Any: signature induk
    ) -> ChatGenerationChunk | None:
        """Konversi chunk stream seperti induknya, ditambah reasoning dari `delta`."""
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if generation_chunk is None or not isinstance(generation_chunk.message, AIMessageChunk):
            return generation_chunk
        reasoning = provider_reasoning(_first_choice_part(chunk, "delta"))
        if reasoning:
            generation_chunk.message.additional_kwargs[REASONING_KWARG] = reasoning
        return generation_chunk

    def _create_chat_result(
        self,
        response: dict[str, Any] | openai.BaseModel,  # Any: respons JSON mentah dari provider
        generation_info: dict[str, Any] | None = None,  # Any: signature induk
    ) -> ChatResult:
        """Hasil non-stream seperti induknya, ditambah reasoning dari `message`."""
        result = super()._create_chat_result(response, generation_info)
        raw_response = response if isinstance(response, dict) else response.model_dump()
        reasoning = provider_reasoning(_first_choice_part(raw_response, "message"))
        message = result.generations[0].message if result.generations else None
        if reasoning and isinstance(message, AIMessage):
            message.additional_kwargs[REASONING_KWARG] = reasoning
        return result


def _first_choice_part(payload: Mapping[str, Any], part: str) -> Mapping[str, Any]:  # Any: JSON
    """`choices[0][part]` dari payload provider, atau dict kosong jika tidak ada."""
    choices = payload.get(CHOICES_KEY) or []
    if not choices:
        return {}
    value = choices[0].get(part)
    return value if isinstance(value, Mapping) else {}
