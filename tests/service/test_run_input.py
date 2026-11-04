import pytest
from fastapi.exceptions import RequestValidationError
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agent_service.agents.base import AgentGraph, BaseAgent
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.llm.fake import FakeModel
from agent_service.schema.requests import UserInput
from agent_service.service.run_input import build_run_input, parse_agent_config
from agent_service.service.thread_access import ThreadNotFoundError

OWNER = "user-a"


@pytest.fixture
def chatbot() -> ChatbotAgent:
    return ChatbotAgent()


@pytest.fixture
def chatbot_graph(chatbot: ChatbotAgent) -> AgentGraph:
    return chatbot.build(FakeModel(), InMemorySaver())


async def test_missing_ids_are_generated(chatbot: ChatbotAgent, chatbot_graph: AgentGraph) -> None:
    run = await build_run_input(UserInput(message="hai"), chatbot, chatbot_graph)

    assert run.thread_id
    assert run.user_id
    assert run.config["configurable"]["thread_id"] == run.thread_id
    assert run.config["metadata"] == {"user_id": run.user_id, "agent_id": "chatbot"}
    assert run.config["run_id"] == run.run_id


async def test_given_ids_are_kept(chatbot: ChatbotAgent, chatbot_graph: AgentGraph) -> None:
    user_input = UserInput(message="hai", thread_id="t1", user_id=OWNER)

    run = await build_run_input(user_input, chatbot, chatbot_graph)

    assert (run.thread_id, run.user_id) == ("t1", OWNER)


async def test_new_thread_gets_human_message(
    chatbot: ChatbotAgent, chatbot_graph: AgentGraph
) -> None:
    run = await build_run_input(UserInput(message="hai"), chatbot, chatbot_graph)

    assert isinstance(run.graph_input, dict)
    assert run.graph_input["messages"] == [HumanMessage(content="hai")]


async def test_run_ids_are_unique(chatbot: ChatbotAgent, chatbot_graph: AgentGraph) -> None:
    first = await build_run_input(UserInput(message="a"), chatbot, chatbot_graph)
    second = await build_run_input(UserInput(message="b"), chatbot, chatbot_graph)

    assert first.run_id != second.run_id


async def test_interrupted_thread_is_resumed(interrupt_agent: BaseAgent) -> None:
    graph = interrupt_agent.build(FakeModel(), InMemorySaver())
    first = await build_run_input(
        UserInput(message="hai", thread_id="t1", user_id=OWNER), interrupt_agent, graph
    )
    await graph.ainvoke(first.graph_input, first.config)

    second = await build_run_input(
        UserInput(message="Budi", thread_id="t1", user_id=OWNER), interrupt_agent, graph
    )

    assert isinstance(second.graph_input, Command)
    assert second.graph_input.resume == "Budi"


async def test_other_users_thread_is_not_found(
    chatbot: ChatbotAgent, chatbot_graph: AgentGraph
) -> None:
    first = await build_run_input(
        UserInput(message="hai", thread_id="t1", user_id=OWNER), chatbot, chatbot_graph
    )
    await chatbot_graph.ainvoke(first.graph_input, first.config)

    with pytest.raises(ThreadNotFoundError):
        await build_run_input(
            UserInput(message="hai", thread_id="t1", user_id="user-b"), chatbot, chatbot_graph
        )


async def test_valid_agent_config_reaches_configurable(tone_agent: BaseAgent) -> None:
    graph = tone_agent.build(FakeModel(), InMemorySaver())
    user_input = UserInput(message="hai", agent_config={"tone": "formal"})

    run = await build_run_input(user_input, tone_agent, graph)

    assert run.config["configurable"]["tone"] == "formal"
    assert run.config["configurable"]["max_words"] == 10


def test_invalid_agent_config_reports_field_location(tone_agent: BaseAgent) -> None:
    with pytest.raises(RequestValidationError) as error_info:
        parse_agent_config(tone_agent, {"max_words": "many", "unknown": 1})

    locations = sorted(tuple(error["loc"]) for error in error_info.value.errors())
    assert locations == [
        ("body", "agent_config", "max_words"),
        ("body", "agent_config", "unknown"),
    ]


def test_default_config_schema_rejects_any_key(chatbot: ChatbotAgent) -> None:
    with pytest.raises(RequestValidationError):
        parse_agent_config(chatbot, {"temperature": 1})
