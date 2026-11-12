from datetime import date
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agent_service.agents.base import AgentGraph
from agent_service.agents.catalog import create_default_agents
from agent_service.agents.interrupt import (
    DEFAULT_QUESTION,
    FUTURE_DATE_QUESTION,
    INTERRUPT_AGENT_ID,
    InterruptAgent,
    parse_iso_date,
    route_after_extract,
    route_start,
    zodiac_sign,
)
from agent_service.llm.fake import FakeModel

TODAY = date(2026, 11, 12)


def extraction(birthdate: str | None, question: str = "Kapan tanggal lahirmu?") -> AIMessage:
    args = {"birthdate": birthdate, "follow_up_question": question}
    return AIMessage(
        content="", tool_calls=[{"name": "BirthdateExtraction", "args": args, "id": "x"}]
    )


def build(*responses: AIMessage | str) -> AgentGraph:
    agent = InterruptAgent(today=lambda: TODAY)
    return agent.build(FakeModel(responses=list(responses)), InMemorySaver())


def config(thread_id: str = "t1") -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id}}


async def ask(graph: AgentGraph, text: str) -> dict[str, Any]:  # Any: state agent
    return await graph.ainvoke({"messages": [HumanMessage(text)]}, config())


async def resume(graph: AgentGraph, answer: str) -> dict[str, Any]:  # Any: state agent
    return await graph.ainvoke(Command(resume=answer), config())


def interrupt_question(result: dict[str, Any]) -> str:  # Any: state agent
    return result["__interrupt__"][0].value


@pytest.mark.parametrize(
    ("birthdate", "sign"),
    [
        (date(1990, 1, 19), "Capricorn"),
        (date(1990, 1, 20), "Aquarius"),
        (date(1990, 3, 21), "Aries"),
        (date(1990, 5, 17), "Taurus"),
        (date(1990, 8, 23), "Virgo"),
        (date(1990, 12, 21), "Sagittarius"),
        (date(1990, 12, 22), "Capricorn"),
    ],
)
def test_zodiac_sign_boundaries(birthdate: date, sign: str) -> None:
    assert zodiac_sign(birthdate) == sign


@pytest.mark.parametrize("raw", [None, "", "17 Mei 1990", "1990-13-01"])
def test_parse_iso_date_rejects_missing_or_invalid(raw: str | None) -> None:
    assert parse_iso_date(raw) is None


def test_routes_follow_known_birthdate() -> None:
    assert route_start({"messages": [], "birthdate": "1990-05-17"}) == "respond"
    assert route_start({"messages": []}) == "extract_birthdate"
    assert route_after_extract({"messages": [], "birthdate": None}) == "ask_birthdate"


async def test_asks_then_answers_after_resume() -> None:
    graph = build(extraction(None), extraction("1990-05-17"), "Zodiakmu Taurus!")

    first = await ask(graph, "Apa zodiakku?")
    second = await resume(graph, "17 Mei 1990")

    assert interrupt_question(first) == "Kapan tanggal lahirmu?"
    assert second["birthdate"] == "1990-05-17"
    assert second["messages"][-1].content == "Zodiakmu Taurus!"
    assert [m.content for m in second["messages"] if isinstance(m, HumanMessage)] == [
        "Apa zodiakku?",
        "17 Mei 1990",
    ]


async def test_answers_directly_when_birthdate_is_in_first_message() -> None:
    graph = build(extraction("1990-05-17"), "Taurus!")

    result = await ask(graph, "Saya lahir 17 Mei 1990, apa zodiakku?")

    assert "__interrupt__" not in result
    assert result["messages"][-1].content == "Taurus!"


async def test_future_date_is_rejected_and_asked_again() -> None:
    graph = build(extraction(None), extraction("2030-01-01"), extraction("1990-05-17"), "Taurus!")

    await ask(graph, "Zodiakku?")
    second = await resume(graph, "1 Januari 2030")
    third = await resume(graph, "17 Mei 1990")

    assert interrupt_question(second) == FUTURE_DATE_QUESTION
    assert third["messages"][-1].content == "Taurus!"


async def test_missing_model_question_falls_back_to_default() -> None:
    graph = build(extraction(None, question=""))

    result = await ask(graph, "Zodiakku?")

    assert interrupt_question(result) == DEFAULT_QUESTION


async def test_known_birthdate_skips_extraction_in_later_turns() -> None:
    graph = build(extraction("1990-05-17"), "Taurus!", "Ya, tetap Taurus.")

    await ask(graph, "Lahir 17 Mei 1990, zodiakku?")
    later = await ask(graph, "Yakin?")

    assert later["messages"][-1].content == "Ya, tetap Taurus."
    assert later["birthdate"] == "1990-05-17"


async def test_extraction_is_not_stored_as_message() -> None:
    graph = build(extraction("1990-05-17"), "Taurus!")

    result = await ask(graph, "Lahir 17 Mei 1990")

    assert [type(m).__name__ for m in result["messages"]] == ["HumanMessage", "AIMessage"]
    assert not result["messages"][-1].tool_calls


def test_registered_in_default_catalog() -> None:
    assert INTERRUPT_AGENT_ID in [agent.agent_id for agent in create_default_agents()]
