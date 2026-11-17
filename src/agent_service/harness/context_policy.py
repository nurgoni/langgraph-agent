"""Anggaran token riwayat dan peringkasan giliran lama sebelum model dipanggil (FR-39, ADR 0002).

Riwayat dibagi menjadi unit: `AIMessage` dengan `tool_calls` selalu satu unit dengan
`ToolMessage`-nya, sehingga pemangkasan tidak pernah memisahkan tool call dari hasilnya. Saat
riwayat (ditambah ringkasan) melewati `max_tokens`, unit lama diringkas sekaligus sampai riwayat
langsung tinggal `keep_ratio` dari anggaran. Giliran berikutnya tidak perlu meringkas lagi sampai
anggaran penuh lagi (keputusan user F29).

Ringkasan dan ID message terakhir yang sudah diringkas disimpan di state thread. Riwayat
`messages` tidak pernah diubah, jadi `/history` tetap lengkap.

>>> from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
>>> call = AIMessage("", tool_calls=[{"name": "calc", "args": {}, "id": "c1"}])
>>> units = message_units([HumanMessage("1+1?"), call, ToolMessage("2", tool_call_id="c1")])
>>> [len(unit) for unit in units]
[1, 2]
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    get_buffer_string,
)
from langchain_core.messages.utils import count_tokens_approximately

from agent_service.core.constants import DEFAULT_CONTEXT_MAX_TOKENS, SKIP_STREAM_TAG
from agent_service.harness.context import SUMMARY_MAX_CHARS, TRUNCATION_MARKER

logger = logging.getLogger(__name__)

# Sama dengan asumsi `count_tokens_approximately`, untuk mengubah token berlebih menjadi karakter.
CHARS_PER_TOKEN: Final = 4
# Setelah meringkas, riwayat langsung tinggal setengah anggaran (keputusan user F29).
DEFAULT_KEEP_RATIO: Final = 0.5
# Ringkasan paling banyak seperempat anggaran, jadi setelah meringkas total input ≤ 75% anggaran.
SUMMARY_BUDGET_DIVISOR: Final = 4
NO_SUMMARY_TEXT: Final = "(none yet)"

SUMMARY_PROMPT: Final = """\
You maintain a running summary of a conversation between a user and an AI assistant. Merge the
new messages into the current summary. Keep facts, names, numbers, decisions, the user's goals and
preferences, results of tool calls that still matter, and open questions. Drop small talk. Write
plain text without a heading, in the language of the conversation, under {max_chars} characters."""
SUMMARY_REQUEST: Final = "Current summary:\n{summary}\n\nNew messages:\n{transcript}"

type TokenCounter = Callable[[Sequence[BaseMessage]], int]


@dataclass(frozen=True)
class ContextWindow:
    """Riwayat yang dikirim ke model pada satu panggilan, beserta ringkasan terbaru.

    Attributes:
        messages: Message sesudah bagian yang sudah diringkas. Isi message yang terlalu besar bisa
            sudah dipotong, tetapi hanya di salinan ini, bukan di state.
        summary: Ringkasan giliran lama, kosong jika belum ada.
        summarized_through: ID message terakhir yang sudah masuk ringkasan, kosong jika belum ada.
    """

    messages: list[BaseMessage]
    summary: str = ""
    summarized_through: str = ""


def message_units(messages: Sequence[BaseMessage]) -> list[list[BaseMessage]]:
    """Kelompokkan message menjadi unit yang tidak boleh dipisah.

    `ToolMessage` selalu ikut unit sebelumnya (unit `AIMessage` yang memanggilnya). Message lain
    menjadi unit sendiri.

    Args:
        messages: Riwayat urut kronologis.

    Returns:
        Unit berurutan. Menggabungkan semua unit menghasilkan `messages` kembali.
    """
    units: list[list[BaseMessage]] = []
    for message in messages:
        if isinstance(message, ToolMessage) and units:
            units[-1].append(message)
            continue
        units.append([message])
    return units


def messages_after(messages: Sequence[BaseMessage], message_id: str) -> list[BaseMessage]:
    """Message sesudah message ber-ID `message_id`, atau semuanya jika ID kosong/tidak ditemukan.

    >>> history = [HumanMessage("a", id="1"), HumanMessage("b", id="2")]
    >>> [message.content for message in messages_after(history, "1")]
    ['b']
    """
    if not message_id:
        return list(messages)
    for index, message in enumerate(messages):
        if message.id == message_id:
            return list(messages[index + 1 :])
    logger.warning("Summarized message %s is not in the thread; using the full history", message_id)
    return list(messages)


class ContextPolicy:
    """Menjaga input riwayat model di bawah `max_tokens` dengan meringkas giliran lama.

    Dibuat sekali per agent dan dipakai semua graph-nya. Model untuk meringkas diberikan per
    panggilan, karena satu agent membangun graph untuk beberapa model.
    """

    def __init__(
        self,
        max_tokens: int = DEFAULT_CONTEXT_MAX_TOKENS,
        keep_ratio: float = DEFAULT_KEEP_RATIO,
        token_counter: TokenCounter = count_tokens_approximately,
    ) -> None:
        """Inisialisasi policy.

        Args:
            max_tokens: Anggaran token riwayat ditambah ringkasan (`CONTEXT_MAX_TOKENS`). System
                prompt di luar anggaran ini, karena setiap bagiannya sudah dibatasi (FR-37).
            keep_ratio: Porsi anggaran untuk riwayat langsung setelah meringkas.
            token_counter: Penghitung token, bisa diganti di test.

        Raises:
            ValueError: Jika `max_tokens` tidak positif atau `keep_ratio` di luar (0, 1).
        """
        if max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {max_tokens}")
        if not 0 < keep_ratio < 1:
            raise ValueError(f"keep_ratio must be between 0 and 1, got {keep_ratio}")
        self._max_tokens = max_tokens
        self._keep_ratio = keep_ratio
        self._count = token_counter

    @property
    def max_tokens(self) -> int:
        """Anggaran token riwayat ditambah ringkasan."""
        return self._max_tokens

    @property
    def summary_max_chars(self) -> int:
        """Batas panjang ringkasan dalam karakter.

        Nilainya `SUMMARY_MAX_CHARS` atau seperempat anggaran (`CHARS_PER_TOKEN` karakter per
        token), mana yang lebih kecil.

        >>> ContextPolicy(max_tokens=16000).summary_max_chars
        4000
        >>> ContextPolicy(max_tokens=400).summary_max_chars
        400
        """
        quarter_budget_chars = self._max_tokens * CHARS_PER_TOKEN // SUMMARY_BUDGET_DIVISOR
        return min(SUMMARY_MAX_CHARS, quarter_budget_chars)

    def tokens(self, messages: Sequence[BaseMessage], summary: str = "") -> int:
        """Perkiraan token `messages` ditambah ringkasan yang ikut dikirim."""
        summary_messages = [SystemMessage(summary)] if summary else []
        return self._count([*messages, *summary_messages])

    async def prepare(
        self,
        model: BaseChatModel,
        messages: Sequence[BaseMessage],
        summary: str = "",
        summarized_through: str = "",
    ) -> ContextWindow:
        """Siapkan riwayat untuk satu panggilan model, meringkas giliran lama bila perlu.

        Args:
            model: Model tanpa tool untuk meringkas (dipanggil dengan tag `skip_stream`).
            messages: Seluruh riwayat thread dari state.
            summary: Ringkasan tersimpan di state.
            summarized_through: ID message terakhir yang sudah masuk `summary`.

        Returns:
            Riwayat yang muat di anggaran dan ringkasan terbaru, untuk disimpan kembali ke state.
        """
        window = messages_after(messages, summarized_through)
        if not window or self.tokens(window, summary) <= self._max_tokens:
            return ContextWindow(window, summary, summarized_through)
        older, recent = self.split(window)
        if older:
            summary = await self._summarize(model, summary, older)
            summarized_through = older[-1].id or summarized_through
        recent_budget = self._max_tokens - self.tokens([], summary)
        return ContextWindow(self.fit(recent, recent_budget), summary, summarized_through)

    def split(self, window: Sequence[BaseMessage]) -> tuple[list[BaseMessage], list[BaseMessage]]:
        """Pisahkan unit lama (untuk diringkas) dari unit terbaru yang muat di `keep_ratio`.

        Unit terakhir selalu dipertahankan, walaupun lebih besar dari porsi itu.

        Args:
            window: Riwayat yang belum diringkas, tidak kosong.

        Returns:
            `(lama, terbaru)`. Gabungan keduanya sama dengan `window`.
        """
        units = message_units(window)
        keep_budget = int(self._max_tokens * self._keep_ratio)
        kept = 1
        used = self._count(units[-1])
        for unit in reversed(units[:-1]):
            used += self._count(unit)
            if used > keep_budget:
                break
            kept += 1
        older = [message for unit in units[:-kept] for message in unit]
        recent = [message for unit in units[-kept:] for message in unit]
        return older, recent

    def fit(self, messages: Sequence[BaseMessage], budget: int) -> list[BaseMessage]:
        """Potong isi message terbesar sampai `messages` muat di `budget` token.

        Hanya terjadi saat satu unit (misalnya hasil tool yang sangat panjang) melebihi anggaran.
        Yang dipotong adalah salinan, dan struktur tool call tetap utuh.

        Args:
            messages: Message yang harus dikirim utuh sebagai satu kesatuan.
            budget: Batas token.

        Returns:
            Salinan `messages` yang muat, atau `messages` apa adanya jika sudah muat.
        """
        fitted = list(messages)
        by_size = sorted(range(len(fitted)), key=lambda i: len(fitted[i].text), reverse=True)
        for index in by_size:
            excess = self._count(fitted) - budget
            if excess <= 0:
                break
            # Penanda `[truncated]` ikut menambah token, dan penghitung membulatkan ke atas.
            remove_chars = (excess + 1) * CHARS_PER_TOKEN + len(TRUNCATION_MARKER)
            fitted[index] = truncate_message(fitted[index], remove_chars)
        return fitted

    async def _summarize(
        self, model: BaseChatModel, summary: str, older: Sequence[BaseMessage]
    ) -> str:
        """Gabungkan `older` ke `summary`, per batch yang masing-masing muat di anggaran.

        Batch membuat thread lama yang sangat panjang tetap bisa diringkas tanpa melebihi konteks
        model. Biasanya hanya ada satu batch.
        """
        summarizer = model.with_config(tags=[SKIP_STREAM_TAG])
        for batch in self._batches(older):
            prompt = [
                SystemMessage(SUMMARY_PROMPT.format(max_chars=self.summary_max_chars)),
                HumanMessage(
                    SUMMARY_REQUEST.format(
                        summary=summary or NO_SUMMARY_TEXT, transcript=get_buffer_string(batch)
                    )
                ),
            ]
            response = await summarizer.ainvoke(prompt)
            summary = self._clean_summary(response, summary)
        logger.info("Summarized %d messages into %d characters", len(older), len(summary))
        return summary

    def _batches(self, older: Sequence[BaseMessage]) -> list[list[BaseMessage]]:
        """Bagi unit lama menjadi batch yang masing-masing muat di anggaran."""
        batches: list[list[BaseMessage]] = [[]]
        for unit in message_units(older):
            fitted = self.fit(unit, self._max_tokens)
            if batches[-1] and self._count([*batches[-1], *fitted]) > self._max_tokens:
                batches.append([])
            batches[-1].extend(fitted)
        return batches

    def _clean_summary(self, response: AIMessage, previous: str) -> str:
        """Teks ringkasan dari respons model, dipotong ke `summary_max_chars`.

        Respons kosong (misalnya model reasoning kehabisan token) mempertahankan ringkasan lama.
        """
        text = response.text.strip()
        if not text:
            logger.warning("Summarization returned no text; keeping the previous summary")
            return previous
        return text[: self.summary_max_chars]


def truncate_message(message: BaseMessage, remove_chars: int) -> BaseMessage:
    """Salinan `message` dengan `remove_chars` karakter terakhir isinya diganti penanda.

    Isi kosong dan isi non-teks (list blok konten) tidak dipotong.

    >>> truncate_message(HumanMessage("abcdefghij"), 4).content
    'abcdef\\n[truncated]'
    """
    if not isinstance(message.content, str) or not message.content:
        return message
    keep = max(len(message.content) - remove_chars, 0)
    return message.model_copy(update={"content": message.content[:keep] + TRUNCATION_MARKER})


if __name__ == "__main__":
    import asyncio

    from agent_service.llm.fake import FakeModel

    async def _demo() -> None:
        history: list[BaseMessage] = []
        for turn in range(6):
            history.append(HumanMessage(f"Question {turn}: " + "detail " * 40, id=f"h{turn}"))
            history.append(AIMessage(f"Answer {turn}.", id=f"a{turn}"))
        policy = ContextPolicy(max_tokens=200)
        window = await policy.prepare(FakeModel(responses=["User asked six questions."]), history)
        print(window.summary, window.summarized_through, len(window.messages))

    asyncio.run(_demo())
