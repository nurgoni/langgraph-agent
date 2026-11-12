import json
import logging
from collections.abc import Awaitable, Callable

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.messages import ChatMessage as LangChainChatMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import interrupt

from agent_service.agents.base import AgentGraph
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.agents.supervisor import create_supervisor_agent
from agent_service.llm.fake import FakeModel
from agent_service.schema.requests import UserInput
from agent_service.schema.responses import ChatMessage
from agent_service.schema.stream import (
    STREAM_EVENT_ADAPTER,
    ErrorEvent,
    MessageEvent,
    ReasoningEvent,
    StreamEvent,
    TokenEvent,
)
from agent_service.service.run_input import build_run_input
from agent_service.service.streaming import (
    DONE_FRAME,
    STREAM_ERROR_DETAIL,
    StreamService,
    sse_frame,
)


@tool
def add(a: int, b: int) -> int:
    """Jumlahkan dua bilangan."""
    return a + b


def parse_frame(frame: str) -> object:
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    return json.loads(frame.removeprefix("data: ").removesuffix("\n\n"))


def test_token_frame_matches_prd_shape() -> None:
    assert parse_frame(sse_frame(TokenEvent(content="Hal"))) == {"type": "token", "content": "Hal"}


def test_message_frame_round_trips_through_adapter() -> None:
    event = MessageEvent(content=ChatMessage(type="ai", content="Halo!", run_id="r1"))

    frame = sse_frame(event)

    payload = frame.removeprefix("data: ").removesuffix("\n\n")
    assert STREAM_EVENT_ADAPTER.validate_json(payload) == event


def test_error_frame_matches_prd_shape() -> None:
    assert parse_frame(sse_frame(ErrorEvent(content="boom"))) == {
        "type": "error",
        "content": "boom",
    }


def test_done_frame_is_literal_marker() -> None:
    assert DONE_FRAME == "data: [DONE]\n\n"


def build_graph(node: Callable[[MessagesState], Awaitable[MessagesState]]) -> AgentGraph:
    """Graph satu node `work` di atas `MessagesState`."""
    # pyrefly tidak mengenali TypedDict sebagai TypedDictLike milik LangGraph.
    builder = StateGraph(MessagesState)  # pyrefly: ignore[bad-specialization]
    # Akibat false positive di atas, tipe state builder tidak ter-resolve oleh pyrefly.
    builder.add_node("work", node)  # pyrefly: ignore[bad-argument-type]
    builder.add_edge(START, "work")
    builder.add_edge("work", END)
    return builder.compile(checkpointer=InMemorySaver())


def build_tool_graph(model: FakeModel) -> AgentGraph:
    """Loop agent → tools → agent sampai model berhenti meminta tool."""

    async def call_model(state: MessagesState) -> MessagesState:
        return {"messages": [await model.ainvoke(state["messages"])]}

    # pyrefly tidak mengenali TypedDict sebagai TypedDictLike milik LangGraph.
    builder = StateGraph(MessagesState)  # pyrefly: ignore[bad-specialization]
    builder.add_node("agent", call_model)
    builder.add_node("tools", ToolNode([add]))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=InMemorySaver())


async def collect(
    graph: AgentGraph, agent_id: str = "test", message: str = "Hai", stream_tokens: bool = True
) -> list[str]:
    agent = ChatbotAgent(agent_id=agent_id)
    run = await build_run_input(
        UserInput(message=message, thread_id="t1", user_id="u1"), agent, graph
    )
    return [frame async for frame in StreamService(graph, run, stream_tokens).stream()]


def events_of(frames: list[str]) -> list[StreamEvent]:
    assert frames[-1] == DONE_FRAME
    events: list[StreamEvent] = []
    for frame in frames[:-1]:
        events.append(STREAM_EVENT_ADAPTER.validate_json(frame.removeprefix("data: ")))
    return events


async def test_tokens_then_final_message_then_done() -> None:
    graph = ChatbotAgent().build(FakeModel(responses=["Halo dunia"]), InMemorySaver())

    events = events_of(await collect(graph, agent_id="chatbot"))

    assert [type(event).__name__ for event in events] == [
        "TokenEvent",
        "TokenEvent",
        "MessageEvent",
    ]
    assert [event.content for event in events[:2]] == ["Halo ", "dunia"]
    final = events[2]
    assert isinstance(final, MessageEvent)
    assert (final.content.type, final.content.content) == ("ai", "Halo dunia")
    assert final.content.run_id


async def test_stream_tokens_false_sends_only_messages() -> None:
    graph = ChatbotAgent().build(FakeModel(responses=["Halo dunia"]), InMemorySaver())

    events = events_of(await collect(graph, agent_id="chatbot", stream_tokens=False))

    assert [type(event).__name__ for event in events] == ["MessageEvent"]


async def test_human_input_is_not_echoed() -> None:
    graph = ChatbotAgent().build(FakeModel(), InMemorySaver())

    events = events_of(await collect(graph, agent_id="chatbot", stream_tokens=False))

    assert all(isinstance(e, MessageEvent) and e.content.type != "human" for e in events)


async def test_tool_call_and_tool_result_are_streamed_as_messages() -> None:
    model = FakeModel(
        responses=[
            AIMessage(
                content="", tool_calls=[{"name": "add", "args": {"a": 1, "b": 2}, "id": "c1"}]
            ),
            "Hasilnya 3",
        ]
    )
    graph = build_tool_graph(model)

    events = events_of(await collect(graph, stream_tokens=False))

    messages = [event.content for event in events if isinstance(event, MessageEvent)]
    assert [(m.type, m.content) for m in messages] == [
        ("ai", ""),
        ("tool", "3"),
        ("ai", "Hasilnya 3"),
    ]
    assert messages[0].tool_calls[0].name == "add"
    assert messages[1].tool_call_id == "c1"


async def test_interrupt_is_streamed_as_ai_message() -> None:
    async def ask(state: MessagesState) -> MessagesState:
        name = interrupt("Siapa namamu?")
        return {"messages": [AIMessage(content=f"Halo {name}")]}

    events = events_of(await collect(build_graph(ask)))

    assert len(events) == 1
    assert isinstance(events[0], MessageEvent)
    assert events[0].content.content == "Siapa namamu?"


async def test_custom_events_become_messages() -> None:
    async def report(state: MessagesState) -> MessagesState:
        writer = get_stream_writer()
        writer({"progress": 50})
        writer(LangChainChatMessage(role="custom", content=[{"progress": 100}]))
        writer("not supported")
        return {"messages": [AIMessage(content="selesai")]}

    events = events_of(await collect(build_graph(report), stream_tokens=False))

    custom = [e.content.custom_data for e in events if isinstance(e, MessageEvent)][:2]
    assert custom == [{"progress": 50}, {"progress": 100}]


async def test_skip_stream_tag_hides_tokens() -> None:
    model = FakeModel(responses=["rahasia internal"]).with_config(tags=["skip_stream"])

    async def classify(state: MessagesState) -> MessagesState:
        await model.ainvoke(state["messages"])
        return {"messages": [AIMessage(content="publik")]}

    events = events_of(await collect(build_graph(classify)))

    assert not any(isinstance(event, TokenEvent) for event in events)


async def test_unsupported_message_is_dropped() -> None:
    async def system(state: MessagesState) -> MessagesState:
        return {"messages": [SystemMessage("aturan"), AIMessage(content="ok")]}

    events = events_of(await collect(build_graph(system), stream_tokens=False))

    assert [e.content.content for e in events if isinstance(e, MessageEvent)] == ["ok"]


async def test_error_mid_stream_sends_error_then_done(caplog: pytest.LogCaptureFixture) -> None:
    async def explode(state: MessagesState) -> MessagesState:
        get_stream_writer()({"step": "before"})
        raise RuntimeError("secret detail")

    with caplog.at_level(logging.ERROR):
        frames = await collect(build_graph(explode))

    events = events_of(frames)
    assert isinstance(events[0], MessageEvent)
    assert events[-1] == ErrorEvent(content=STREAM_ERROR_DETAIL)
    assert "secret detail" not in "".join(frames)
    assert "Stream failed" in caplog.text


async def test_client_disconnect_closes_without_done() -> None:
    graph = ChatbotAgent().build(FakeModel(responses=["satu dua tiga"]), InMemorySaver())
    agent = ChatbotAgent()
    run = await build_run_input(UserInput(message="Hai"), agent, graph)
    stream = StreamService(graph, run, stream_tokens=True).stream()

    first = await anext(stream)
    await stream.aclose()

    assert first != DONE_FRAME


REASONED_ANSWER = AIMessage(
    content="Merah dan biru", additional_kwargs={"reasoning_content": "Pilih dua warna"}
)


async def test_reasoning_frames_come_before_answer_tokens() -> None:
    graph = ChatbotAgent().build(FakeModel(responses=[REASONED_ANSWER]), InMemorySaver())

    events = events_of(await collect(graph, agent_id="chatbot"))

    kinds = [type(event).__name__ for event in events]
    first_token = kinds.index("TokenEvent")
    assert set(kinds[:first_token]) == {"ReasoningEvent"}
    reasoning = "".join(e.content for e in events if isinstance(e, ReasoningEvent))
    assert reasoning == "Pilih dua warna"
    final = events[-1]
    assert isinstance(final, MessageEvent)
    assert final.content.reasoning == "Pilih dua warna"


async def test_stream_tokens_false_also_hides_reasoning_frames() -> None:
    graph = ChatbotAgent().build(FakeModel(responses=[REASONED_ANSWER]), InMemorySaver())

    events = events_of(await collect(graph, agent_id="chatbot", stream_tokens=False))

    [final] = events
    assert isinstance(final, MessageEvent)
    assert final.content.reasoning == "Pilih dua warna"


async def test_skip_stream_tag_hides_reasoning() -> None:
    model = FakeModel(responses=[REASONED_ANSWER]).with_config(tags=["skip_stream"])

    async def classify(state: MessagesState) -> MessagesState:
        await model.ainvoke(state["messages"])
        return {"messages": [AIMessage(content="publik")]}

    events = events_of(await collect(build_graph(classify)))

    assert not any(isinstance(event, ReasoningEvent) for event in events)


async def test_model_without_reasoning_sends_no_reasoning_frames() -> None:
    graph = ChatbotAgent().build(FakeModel(responses=["Halo dunia"]), InMemorySaver())

    events = events_of(await collect(graph, agent_id="chatbot"))

    assert not any(isinstance(event, ReasoningEvent) for event in events)


class NoSearch:
    def text(self, query: str, max_results: int) -> list[dict[str, str]]:
        return []


async def test_supervisor_streams_expert_messages_marked_and_no_expert_tokens() -> None:
    model = FakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "ask_math_expert", "args": {"task": "1 + 1"}, "id": "s1"}],
            ),
            "Expert says two",
            "Supervisor says two",
        ]
    )
    graph = create_supervisor_agent(NoSearch()).build(model, InMemorySaver())

    events = events_of(await collect(graph, agent_id="supervisor"))

    tokens = "".join(e.content for e in events if isinstance(e, TokenEvent))
    messages = [e.content for e in events if isinstance(e, MessageEvent)]
    assert tokens == "Supervisor says two"
    assert [(m.type, m.agent, m.content) for m in messages] == [
        ("ai", None, ""),
        ("ai", "math_expert", "Expert says two"),
        ("tool", None, "Expert says two"),
        ("ai", None, "Supervisor says two"),
    ]


async def test_expert_steps_stream_before_delegation_finishes() -> None:
    model = FakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "ask_math_expert", "args": {"task": "1 + 1"}, "id": "s1"}],
            ),
            AIMessage(
                content="",
                tool_calls=[{"name": "calculator", "args": {"expression": "1 + 1"}, "id": "c1"}],
            ),
            "Expert says two",
            "Supervisor says two",
        ]
    )
    graph = create_supervisor_agent(NoSearch()).build(model, InMemorySaver())
    custom_messages = []
    async for mode, payload in graph.astream(
        {"messages": [HumanMessage("1 + 1?")]},
        {"configurable": {"thread_id": "t1"}},
        stream_mode=["custom", "updates"],
    ):
        if mode == "custom":
            custom_messages.append(payload)
        elif "delegate" in payload:
            break

    assert [type(m).__name__ for m in custom_messages] == ["AIMessage", "ToolMessage", "AIMessage"]


async def test_expert_messages_are_not_sent_twice() -> None:
    model = FakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "ask_math_expert", "args": {"task": "1 + 1"}, "id": "s1"}],
            ),
            AIMessage(
                content="",
                tool_calls=[{"name": "calculator", "args": {"expression": "1 + 1"}, "id": "c1"}],
            ),
            "Expert says two",
            "Supervisor says two",
        ]
    )
    graph = create_supervisor_agent(NoSearch()).build(model, InMemorySaver())

    events = events_of(await collect(graph, agent_id="supervisor", stream_tokens=False))

    expert = [e.content for e in events if isinstance(e, MessageEvent) and e.content.agent]
    assert [(m.type, m.content) for m in expert] == [
        ("ai", ""),
        ("tool", "2"),
        ("ai", "Expert says two"),
    ]


async def test_subagent_tag_hides_tokens_explicitly() -> None:
    model = FakeModel(responses=["rahasia expert"]).with_config(tags=["subagent"])

    async def expert(state: MessagesState) -> MessagesState:
        await model.ainvoke(state["messages"])
        return {"messages": [AIMessage(content="publik")]}

    events = events_of(await collect(build_graph(expert)))

    assert not any(isinstance(event, TokenEvent) for event in events)
