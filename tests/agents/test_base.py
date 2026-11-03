import pytest
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import MessagesState, StateGraph
from pydantic import BaseModel, ConfigDict, ValidationError

from agent_service.agents.base import AgentGraph, BaseAgent, Checkpointer, EmptyAgentConfig
from agent_service.llm.fake import FakeModel


class EchoAgent(BaseAgent):
    def build(self, model: BaseChatModel, checkpointer: Checkpointer) -> AgentGraph:
        # pyrefly tidak mengenali TypedDict sebagai TypedDictLike milik LangGraph.
        builder = StateGraph(MessagesState)  # pyrefly: ignore[bad-specialization]
        builder.add_node("noop", lambda state: {})
        builder.set_entry_point("noop")
        return builder.compile(checkpointer=checkpointer)


class TemperatureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float = 0.0


class ConfigurableAgent(EchoAgent):
    config_schema = TemperatureConfig


def test_identity_is_set_from_constructor() -> None:
    agent = EchoAgent(agent_id="echo", description="Echo agent")

    assert (agent.agent_id, agent.description) == ("echo", "Echo agent")
    assert repr(agent) == "EchoAgent(agent_id='echo')"


async def test_default_load_is_noop() -> None:
    await EchoAgent("echo", "Echo agent").load()


def test_build_compiles_with_given_checkpointer() -> None:
    checkpointer = InMemorySaver()

    graph = EchoAgent("echo", "Echo agent").build(FakeModel(), checkpointer)

    assert graph.checkpointer is checkpointer


def test_default_config_schema_accepts_empty_config() -> None:
    config = EchoAgent("echo", "Echo agent").parse_config({})

    assert isinstance(config, EmptyAgentConfig)


def test_default_config_schema_rejects_unknown_key() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        EchoAgent("echo", "Echo agent").parse_config({"temperature": 1})


def test_custom_config_schema_is_used() -> None:
    config = ConfigurableAgent("configurable", "Configurable agent").parse_config(
        {"temperature": 0.7}
    )

    assert config == TemperatureConfig(temperature=0.7)


def test_custom_config_schema_rejects_invalid_value() -> None:
    with pytest.raises(ValidationError):
        ConfigurableAgent("configurable", "Configurable agent").parse_config({"temperature": "hot"})


def test_base_agent_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        BaseAgent("base", "Abstract")  # pyrefly: ignore[bad-instantiation]
