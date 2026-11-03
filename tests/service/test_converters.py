from pydantic import BaseModel

from agent_service.agents.chatbot import ChatbotAgent
from agent_service.service.converters import agent_to_info


class LimitConfig(BaseModel):
    max_steps: int = 3


class LimitedAgent(ChatbotAgent):
    config_schema = LimitConfig


def test_agent_to_info_copies_identity() -> None:
    info = agent_to_info(ChatbotAgent(agent_id="bot", description="A bot"))

    assert (info.key, info.description) == ("bot", "A bot")


def test_default_config_schema_forbids_extra_keys() -> None:
    info = agent_to_info(ChatbotAgent())

    assert info.config_schema["additionalProperties"] is False
    assert info.config_schema.get("properties", {}) == {}


def test_custom_config_schema_is_exported_as_json_schema() -> None:
    info = agent_to_info(LimitedAgent())

    assert info.config_schema == LimitConfig.model_json_schema()
