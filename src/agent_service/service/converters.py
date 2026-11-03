"""Transformasi murni dari objek agent/LangChain ke schema API.

Ditulis sebagai function karena tanpa state (AGENTS.md § Class vs Function). Letaknya di
`service/`, bukan `schema/`, supaya schema tidak bergantung pada agent maupun LangChain.
"""

from agent_service.agents.base import BaseAgent
from agent_service.schema.responses import AgentInfo


def agent_to_info(agent: BaseAgent) -> AgentInfo:
    """Ubah agent menjadi `AgentInfo`, termasuk JSON Schema `agent_config` (FR-27).

    Args:
        agent: Agent terdaftar.

    Returns:
        Informasi publik agent untuk `/info`.

    >>> from agent_service.agents.chatbot import ChatbotAgent
    >>> info = agent_to_info(ChatbotAgent())
    >>> info.key, info.config_schema["additionalProperties"]
    ('chatbot', False)
    """
    return AgentInfo(
        key=agent.agent_id,
        description=agent.description,
        config_schema=agent.config_schema.model_json_schema(),
    )
