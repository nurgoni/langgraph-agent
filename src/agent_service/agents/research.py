"""Research assistant: `ToolCallingAgent` dengan web search dan kalkulator."""

from typing import Final

from agent_service.agents.tool_calling import ToolCallingAgent
from agent_service.agents.tools.calculator import calculator
from agent_service.agents.tools.web_search import (
    SearchBackend,
    UnconfiguredSearch,
    create_web_search_tool,
)

RESEARCH_ASSISTANT_ID: Final = "research-assistant"
RESEARCH_ASSISTANT_DESCRIPTION: Final = (
    "A research assistant that searches the web and uses a calculator, citing its sources."
)
# Prompt berbahasa Inggris karena dibaca model. `{current_date}` diisi saat model dipanggil.
RESEARCH_SYSTEM_PROMPT: Final = """\
You are a helpful research assistant with access to web search and a calculator.
Today's date is {current_date}.

The user cannot see tool results, so put everything that matters into your answer.
- Use web_search for current events or facts you are not sure about. Cite one or two sources as
  markdown links, and only use links returned by web_search.
- Use calculator for any arithmetic. In your answer, write the math in plain notation such as
  "300 * 200", not numexpr syntax.
- If a tool fails, say so briefly and answer with what you know.
- Answer in the same language as the user."""


def create_research_assistant(search_backend: SearchBackend | None = None) -> ToolCallingAgent:
    """Buat research assistant dengan tool web search dan kalkulator.

    Function, bukan class: factory konfigurasi untuk `ToolCallingAgent`, tanpa state sendiri.

    Args:
        search_backend: Mesin pencari untuk tool web search. Default: `UnconfiguredSearch`
            (tool menjawab "not configured").

    Returns:
        Agent `research-assistant` yang siap didaftarkan.

    >>> agent = create_research_assistant()
    >>> agent.agent_id
    'research-assistant'
    """
    backend = UnconfiguredSearch() if search_backend is None else search_backend
    tools = [create_web_search_tool(backend), calculator]
    return ToolCallingAgent(
        agent_id=RESEARCH_ASSISTANT_ID,
        description=RESEARCH_ASSISTANT_DESCRIPTION,
        tools=tools,
        system_prompt=RESEARCH_SYSTEM_PROMPT,
    )
