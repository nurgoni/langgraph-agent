from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

from agent_service.agents.catalog import create_default_agents
from agent_service.agents.research import (
    RESEARCH_ASSISTANT_ID,
    RESEARCH_SYSTEM_PROMPT,
    create_research_assistant,
)
from agent_service.llm.fake import FakeModel


class FakeSearch:
    """Mesin pencari tiruan, supaya test tidak membuka koneksi."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def text(self, query: str, max_results: int) -> Sequence[Mapping[str, Any]]:
        self.queries.append(query)
        return [{"title": "LangGraph 1.2", "href": "https://example.com/lg", "body": "Released"}]


def call(name: str, args: dict[str, str], call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def test_registered_in_default_catalog() -> None:
    agent_ids = [agent.agent_id for agent in create_default_agents()]

    assert RESEARCH_ASSISTANT_ID in agent_ids


def test_prompt_mentions_both_tools_and_date_placeholder() -> None:
    assert "{current_date}" in RESEARCH_SYSTEM_PROMPT
    assert "web_search" in RESEARCH_SYSTEM_PROMPT
    assert "calculator" in RESEARCH_SYSTEM_PROMPT


async def test_searches_calculates_then_cites() -> None:
    search = FakeSearch()
    model = FakeModel(
        responses=[
            call("web_search", {"query": "langgraph release"}, "s1"),
            call("calculator", {"expression": "2026 - 2024"}, "c1"),
            "LangGraph 1.2 dirilis ([sumber](https://example.com/lg)), 2 tahun setelah 2024.",
        ]
    )
    graph = create_research_assistant(search).build(model, InMemorySaver())
    config: RunnableConfig = {"configurable": {"thread_id": "r1"}}

    result = await graph.ainvoke({"messages": [HumanMessage("Kapan LangGraph 1.2?")]}, config)

    tool_results = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert search.queries == ["langgraph release"]
    assert "[LangGraph 1.2](https://example.com/lg)" in str(tool_results[0].content)
    assert tool_results[1].content == "2"
    assert "https://example.com/lg" in str(result["messages"][-1].content)
