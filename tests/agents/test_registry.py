import logging

import pytest
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import MessagesState, StateGraph

from agent_service.agents.base import AgentGraph, BaseAgent, Checkpointer
from agent_service.agents.errors import (
    AgentNotFoundError,
    AgentUnavailableError,
    DuplicateAgentError,
)
from agent_service.agents.registry import AgentRegistry
from agent_service.core.constants import FAKE_MODEL_NAME
from agent_service.core.settings import Settings
from agent_service.llm.factory import ModelFactory, UnknownModelError
from agent_service.llm.fake import FakeModel

OTHER_MODEL = "gpt-test"


class RecordingAgent(BaseAgent):
    """Agent fake yang mencatat setiap model yang dipakai `build`."""

    def __init__(self, agent_id: str = "recording") -> None:
        super().__init__(agent_id=agent_id, description="Records build calls")
        self.built_with: list[BaseChatModel] = []
        self.load_calls = 0

    async def load(self) -> None:
        self.load_calls += 1

    def build(self, model: BaseChatModel, checkpointer: Checkpointer) -> AgentGraph:
        self.built_with.append(model)
        # pyrefly tidak mengenali TypedDict sebagai TypedDictLike milik LangGraph.
        builder = StateGraph(MessagesState)  # pyrefly: ignore[bad-specialization]
        builder.add_node("noop", lambda state: {})
        builder.set_entry_point("noop")
        return builder.compile(checkpointer=checkpointer)


class FailingLoadAgent(RecordingAgent):
    async def load(self) -> None:
        raise ConnectionError("mcp server is down")


class FailingBuildAgent(RecordingAgent):
    def build(self, model: BaseChatModel, checkpointer: Checkpointer) -> AgentGraph:
        raise ValueError("invalid graph")


@pytest.fixture
def model_factory() -> ModelFactory:
    settings = Settings(
        _env_file=None,
        use_fake_model=True,
        llm_base_url="http://llm.test/v1",
        llm_api_key="sk-test",
        default_model=FAKE_MODEL_NAME,
        available_models=[FAKE_MODEL_NAME, OTHER_MODEL],
    )
    return ModelFactory(settings)


@pytest.fixture
def checkpointer() -> InMemorySaver:
    return InMemorySaver()


@pytest.fixture
def registry(model_factory: ModelFactory, checkpointer: InMemorySaver) -> AgentRegistry:
    return AgentRegistry(model_factory, checkpointer)


def test_duplicate_agent_id_is_rejected(registry: AgentRegistry) -> None:
    registry.register(RecordingAgent("same"))

    with pytest.raises(DuplicateAgentError):
        registry.register(RecordingAgent("same"))


def test_unknown_agent_is_not_found(registry: AgentRegistry) -> None:
    with pytest.raises(AgentNotFoundError) as error_info:
        registry.get_graph("missing")

    assert error_info.value.agent_id == "missing"


def test_get_agent_returns_registered_agent(registry: AgentRegistry) -> None:
    agent = RecordingAgent()
    registry.register(agent)

    assert registry.get_agent(agent.agent_id) is agent


def test_agent_is_unavailable_before_load(registry: AgentRegistry) -> None:
    registry.register(RecordingAgent())

    assert not registry.is_available("recording")
    with pytest.raises(AgentUnavailableError):
        registry.get_graph("recording")


async def test_load_all_compiles_default_graph_with_checkpointer(
    registry: AgentRegistry, checkpointer: InMemorySaver
) -> None:
    agent = RecordingAgent()
    registry.register(agent)

    await registry.load_all()

    assert agent.load_calls == 1
    assert len(agent.built_with) == 1
    assert isinstance(agent.built_with[0], FakeModel)
    assert registry.get_graph("recording").checkpointer is checkpointer


async def test_failed_load_does_not_stop_other_agents(
    registry: AgentRegistry, caplog: pytest.LogCaptureFixture
) -> None:
    registry.register(FailingLoadAgent("broken"))
    registry.register(RecordingAgent("healthy"))

    with caplog.at_level(logging.ERROR):
        await registry.load_all()

    assert not registry.is_available("broken")
    assert registry.is_available("healthy")
    assert "'broken' failed to load" in caplog.text
    with pytest.raises(AgentUnavailableError):
        registry.get_graph("broken")


async def test_failed_build_marks_agent_unavailable(registry: AgentRegistry) -> None:
    registry.register(FailingBuildAgent("broken"))

    await registry.load_all()

    assert not registry.is_available("broken")


async def test_load_all_skips_agents_already_loaded(registry: AgentRegistry) -> None:
    agent = RecordingAgent()
    registry.register(agent)

    await registry.load_all()
    await registry.load_all()

    assert agent.load_calls == 1


async def test_same_model_reuses_graph(registry: AgentRegistry) -> None:
    agent = RecordingAgent()
    registry.register(agent)
    await registry.load_all()

    assert registry.get_graph("recording") is registry.get_graph("recording", FAKE_MODEL_NAME)
    assert len(agent.built_with) == 1


async def test_different_model_builds_different_graph(registry: AgentRegistry) -> None:
    agent = RecordingAgent()
    registry.register(agent)
    await registry.load_all()

    default_graph = registry.get_graph("recording")
    other_graph = registry.get_graph("recording", OTHER_MODEL)

    assert other_graph is not default_graph
    assert getattr(agent.built_with[-1], "model_name", None) == OTHER_MODEL


async def test_model_outside_allowlist_is_rejected(registry: AgentRegistry) -> None:
    registry.register(RecordingAgent())
    await registry.load_all()

    with pytest.raises(UnknownModelError):
        registry.get_graph("recording", "gpt-unknown")


def test_list_agents_keeps_registration_order(registry: AgentRegistry) -> None:
    first, second = RecordingAgent("b-first"), RecordingAgent("a-second")
    registry.register(first)
    registry.register(second)

    assert registry.list_agents() == [first, second]
