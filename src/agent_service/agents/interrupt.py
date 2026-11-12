"""Agent human-in-the-loop: bertanya lewat `interrupt()` jika informasi yang dibutuhkan belum ada.

Contohnya menghitung zodiak. Jika tanggal lahir belum diketahui, graph berhenti dengan pertanyaan.
Jawaban user (lewat `Command(resume=...)`) masuk sebagai message baru, lalu graph mencoba
mengekstrak lagi. Ulangan ini berjalan lewat edge graph, bukan rekursi, dan setiap node hanya
mengembalikan update state, tanpa memutasi state.
"""

from collections.abc import Callable
from datetime import date
from typing import Final, Literal, NotRequired

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from agent_service.agents.base import AgentGraph, BaseAgent, Checkpointer

INTERRUPT_AGENT_ID: Final = "interrupt-agent"
INTERRUPT_AGENT_DESCRIPTION: Final = (
    "Asks for your birthdate when it is missing, then tells you your zodiac sign."
)
EXTRACT_NODE: Final = "extract_birthdate"
ASK_NODE: Final = "ask_birthdate"
RESPOND_NODE: Final = "respond"
# Panggilan LLM internal: hasilnya data terstruktur, bukan teks untuk user.
SKIP_STREAM_TAG: Final = "skip_stream"
DEFAULT_QUESTION: Final = "What is your birthdate? Please use YYYY-MM-DD, for example 1990-05-17."
FUTURE_DATE_QUESTION: Final = (
    "That date is in the future. What is your birthdate? Please use YYYY-MM-DD."
)
DISPLAY_DATE_FORMAT: Final = "%B %d, %Y"

EXTRACTION_PROMPT: Final = """\
You extract the user's birthdate from the conversation.
- Look only at what the user wrote. Accept any date format and convert it to YYYY-MM-DD.
- If the user has not given a full birthdate (day, month and year), return null.
- Always write follow_up_question in the user's language, asking for their birthdate."""

RESPONSE_PROMPT: Final = """\
You are a friendly assistant. The user's birthdate is {birthdate} and their zodiac sign is
{zodiac_sign}. Answer the user's latest message using this information. If they ask for their
zodiac sign, tell them and add one short fun fact about it. Answer in the same language as the
user."""

# (bulan, hari terakhir, zodiak): tanggal sampai batas ini masuk zodiak tersebut.
ZODIAC_LAST_DAYS: Final = (
    (1, 19, "Capricorn"),
    (2, 18, "Aquarius"),
    (3, 20, "Pisces"),
    (4, 19, "Aries"),
    (5, 20, "Taurus"),
    (6, 20, "Gemini"),
    (7, 22, "Cancer"),
    (8, 22, "Leo"),
    (9, 22, "Virgo"),
    (10, 22, "Libra"),
    (11, 21, "Scorpio"),
    (12, 21, "Sagittarius"),
    (12, 31, "Capricorn"),
)

type Today = Callable[[], date]
type ExtractRoute = Literal["ask_birthdate", "respond"]
type StartRoute = Literal["extract_birthdate", "respond"]


class BirthdateExtraction(BaseModel):
    """Birthdate found in the conversation, and the question to ask if it is missing."""

    birthdate: str | None = Field(
        description="The user's birthdate as YYYY-MM-DD, or null if they have not given it."
    )
    follow_up_question: str = Field(
        description="A short question asking for the birthdate, in the user's language."
    )


class InterruptState(MessagesState):
    """Riwayat message, tanggal lahir yang sudah valid (ISO), dan pertanyaan yang akan diajukan."""

    birthdate: NotRequired[str | None]
    question: NotRequired[str]


def parse_iso_date(raw: str | None) -> date | None:
    """Ubah teks `YYYY-MM-DD` dari model menjadi tanggal, atau `None` jika kosong atau tidak valid.

    >>> parse_iso_date("1990-05-17")
    datetime.date(1990, 5, 17)
    >>> parse_iso_date("17 Mei 1990") is None
    True
    """
    if not raw:
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def zodiac_sign(birthdate: date) -> str:
    """Zodiak barat untuk tanggal lahir, dihitung di kode supaya tidak bergantung pada model.

    >>> zodiac_sign(date(1990, 5, 17))
    'Taurus'
    >>> zodiac_sign(date(2000, 12, 25))
    'Capricorn'
    """
    for month, last_day, sign in ZODIAC_LAST_DAYS:
        if (birthdate.month, birthdate.day) <= (month, last_day):
            return sign
    return ZODIAC_LAST_DAYS[-1][2]


def route_start(state: InterruptState) -> StartRoute:
    """Lewati ekstraksi jika tanggal lahir sudah diketahui dari giliran sebelumnya."""
    return RESPOND_NODE if state.get("birthdate") else EXTRACT_NODE


def route_after_extract(state: InterruptState) -> ExtractRoute:
    """Tanya user jika tanggal lahir belum valid, selain itu jawab."""
    return RESPOND_NODE if state.get("birthdate") else ASK_NODE


def ask_birthdate(state: InterruptState) -> dict[str, list[HumanMessage]]:
    """Berhenti dan tanyakan tanggal lahir. Jawaban user menjadi message baru di riwayat.

    Node murni (function, bukan method): tidak butuh model. Saat graph dilanjutkan dengan
    `Command(resume=jawaban)`, node ini dijalankan ulang dan `interrupt()` mengembalikan jawaban.
    """
    answer = interrupt(state.get("question") or DEFAULT_QUESTION)
    return {"messages": [HumanMessage(content=str(answer))]}


class InterruptAgent(BaseAgent):
    """Agent zodiak yang menanyakan tanggal lahir lewat `interrupt()` jika belum diketahui."""

    def __init__(
        self,
        agent_id: str = INTERRUPT_AGENT_ID,
        description: str = INTERRUPT_AGENT_DESCRIPTION,
        today: Today = date.today,
    ) -> None:
        """Inisialisasi agent.

        Args:
            agent_id: ID agent di registry.
            description: Deskripsi untuk `/info`.
            today: Sumber tanggal hari ini, bisa diganti di test.
        """
        super().__init__(agent_id=agent_id, description=description)
        self._today = today

    def build(self, model: BaseChatModel, checkpointer: Checkpointer) -> AgentGraph:
        """Compile graph `extract → (ask → extract)* → respond`.

        Args:
            model: Chat model untuk ekstraksi dan jawaban.
            checkpointer: Saver tempat riwayat dan tanggal lahir thread disimpan.

        Returns:
            Graph yang sudah di-compile.
        """
        extractor = model.with_structured_output(
            BirthdateExtraction, method="function_calling"
        ).with_config(tags=[SKIP_STREAM_TAG])

        # Closure, bukan method: satu instance agent membangun graph untuk beberapa model.
        async def extract_birthdate(state: InterruptState) -> dict[str, str | None]:
            prompt = SystemMessage(content=EXTRACTION_PROMPT)
            extraction = await extractor.ainvoke([prompt, *state["messages"]])
            return self._extraction_update(BirthdateExtraction.model_validate(extraction))

        async def respond(state: InterruptState) -> dict[str, list[AIMessage]]:
            birthdate = date.fromisoformat(str(state.get("birthdate")))
            prompt = SystemMessage(
                content=RESPONSE_PROMPT.format(
                    birthdate=birthdate.strftime(DISPLAY_DATE_FORMAT),
                    zodiac_sign=zodiac_sign(birthdate),
                )
            )
            return {"messages": [await model.ainvoke([prompt, *state["messages"]])]}

        # pyrefly tidak mengenali TypedDict sebagai TypedDictLike milik LangGraph.
        builder = StateGraph(InterruptState)  # pyrefly: ignore[bad-specialization]
        builder.add_node(EXTRACT_NODE, extract_birthdate)
        builder.add_node(ASK_NODE, ask_birthdate)
        builder.add_node(RESPOND_NODE, respond)
        builder.add_conditional_edges(START, route_start)
        builder.add_conditional_edges(EXTRACT_NODE, route_after_extract)
        builder.add_edge(ASK_NODE, EXTRACT_NODE)
        builder.add_edge(RESPOND_NODE, END)
        return builder.compile(checkpointer=checkpointer)

    def _extraction_update(self, extraction: BirthdateExtraction) -> dict[str, str | None]:
        """Update state dari hasil ekstraksi: tanggal lahir valid, atau pertanyaan untuk user.

        Tanggal di masa depan ditolak dengan pertanyaan khusus. Tanggal kosong atau tidak valid
        memakai pertanyaan dari model, yang ditulis dalam bahasa user.
        """
        candidate = parse_iso_date(extraction.birthdate)
        if candidate is not None and candidate <= self._today():
            return {"birthdate": candidate.isoformat()}
        if candidate is not None:
            return {"birthdate": None, "question": FUTURE_DATE_QUESTION}
        return {"birthdate": None, "question": extraction.follow_up_question or DEFAULT_QUESTION}


if __name__ == "__main__":
    import asyncio

    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command

    from agent_service.llm.fake import FakeModel

    def extraction_call(birthdate: str | None) -> AIMessage:
        args = {"birthdate": birthdate, "follow_up_question": "Kapan tanggal lahirmu?"}
        return AIMessage(
            content="",
            tool_calls=[{"name": "BirthdateExtraction", "args": args, "id": "x"}],
        )

    async def _demo() -> None:
        model = FakeModel(
            responses=[extraction_call(None), extraction_call("1990-05-17"), "Zodiakmu Taurus!"]
        )
        graph = InterruptAgent().build(model, InMemorySaver())
        config = {"configurable": {"thread_id": "demo"}}
        first = await graph.ainvoke({"messages": [("human", "Apa zodiakku?")]}, config)
        print("interrupt:", first["__interrupt__"][0].value)
        second = await graph.ainvoke(Command(resume="17 Mei 1990"), config)
        print("answer:", second["messages"][-1].content, "| birthdate:", second["birthdate"])

    asyncio.run(_demo())
