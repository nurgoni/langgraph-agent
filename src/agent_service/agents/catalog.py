"""Daftar agent bawaan dan project built-in yang disiapkan service saat startup.

>>> [project.base_agent_id for project in BUILTIN_PROJECTS]
['chatbot', 'research-assistant']
"""

from dataclasses import dataclass
from typing import Final

from agent_service.agents.base import BaseAgent
from agent_service.agents.chatbot import CHATBOT_AGENT_ID, ChatbotAgent
from agent_service.agents.interrupt import InterruptAgent
from agent_service.agents.research import RESEARCH_ASSISTANT_ID, create_research_assistant
from agent_service.agents.supervisor import create_supervisor_agent
from agent_service.agents.tools.web_search import SearchBackend
from agent_service.harness.skills.toolkit import SkillToolkit

DEFAULT_AGENT_ID: Final = CHATBOT_AGENT_ID


def create_default_agents(
    search_backend: SearchBackend | None = None, skills: SkillToolkit | None = None
) -> list[BaseAgent]:
    """Buat instance baru untuk setiap agent bawaan.

    Function, bukan class: factory tanpa state. Instance baru di setiap panggilan supaya
    setiap app (dan setiap test) punya agent sendiri.

    Args:
        search_backend: Mesin pencari untuk tool web search. Default: tanpa pencarian.
        skills: Toolkit skill untuk chatbot dan research assistant. Default: tanpa skill.

    Returns:
        Agent bawaan, urut sesuai tampilan di `/info`.

    >>> [agent.agent_id for agent in create_default_agents()]
    ['chatbot', 'research-assistant', 'interrupt-agent', 'supervisor']
    >>> DEFAULT_AGENT_ID
    'chatbot'
    """
    return [
        ChatbotAgent(skills=skills),
        create_research_assistant(search_backend, skills),
        InterruptAgent(),
        create_supervisor_agent(search_backend),
    ]


@dataclass(frozen=True)
class BuiltinProject:
    """Project built-in (ADR 0004): read-only, terlihat oleh semua user, di-seed saat startup.

    Didefinisikan sebagai data di sini, bukan di database, supaya isinya ikut versi kode. Service
    meng-upsert-nya berdasarkan `project_id` di setiap startup.
    """

    project_id: str
    name: str
    description: str
    base_agent_id: str
    instructions: str = ""
    skill_ids: tuple[str, ...] = ()


BUILTIN_PROJECTS: Final = (
    BuiltinProject(
        project_id="general-assistant",
        name="General Assistant",
        description="Everyday questions, writing, and brainstorming.",
        base_agent_id=CHATBOT_AGENT_ID,
        instructions="Keep answers concise. Use bullet points when listing several items.",
        skill_ids=("builtin/meeting-notes",),
    ),
    BuiltinProject(
        project_id="research-assistant",
        name="Research Assistant",
        description="Researches a topic on the web and answers with cited sources.",
        base_agent_id=RESEARCH_ASSISTANT_ID,
        instructions=(
            "Search before answering questions about recent events or facts you are unsure of. "
            "End every answer with a short list of the sources you used."
        ),
        skill_ids=("builtin/research-report",),
    ),
)
