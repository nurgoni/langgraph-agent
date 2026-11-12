"""Daftar agent bawaan yang didaftarkan service saat startup."""

from typing import Final

from agent_service.agents.base import BaseAgent
from agent_service.agents.chatbot import CHATBOT_AGENT_ID, ChatbotAgent
from agent_service.agents.interrupt import InterruptAgent
from agent_service.agents.research import create_research_assistant
from agent_service.agents.supervisor import create_supervisor_agent

DEFAULT_AGENT_ID: Final = CHATBOT_AGENT_ID


def create_default_agents() -> list[BaseAgent]:
    """Buat instance baru untuk setiap agent bawaan.

    Function, bukan class: factory tanpa state. Instance baru di setiap panggilan supaya
    setiap app (dan setiap test) punya agent sendiri.

    Returns:
        Agent bawaan, urut sesuai tampilan di `/info`.

    >>> [agent.agent_id for agent in create_default_agents()]
    ['chatbot', 'research-assistant', 'interrupt-agent', 'supervisor']
    >>> DEFAULT_AGENT_ID
    'chatbot'
    """
    return [
        ChatbotAgent(),
        create_research_assistant(),
        InterruptAgent(),
        create_supervisor_agent(),
    ]
