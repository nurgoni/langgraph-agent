"""Agent memakai skill lewat `SkillToolkit` (F28): indeks di prompt dan tool `load_skill`."""

from collections.abc import Callable, Iterator, Sequence
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import PrivateAttr

from agent_service.agents.chatbot import ChatbotAgent
from agent_service.agents.research import create_research_assistant
from agent_service.agents.tool_calling import ToolCallingAgent
from agent_service.harness.skills.registry import SkillRegistry
from agent_service.harness.skills.sources import BUILTIN_SKILLS_DIR, FilesystemSkillSource
from agent_service.harness.skills.toolkit import SkillToolkit
from agent_service.llm.fake import FakeModel

NOTES = "builtin/meeting-notes"
REPORT = "builtin/research-report"


class BindingRecorder(FakeModel):
    """FakeModel yang mencatat tool yang terikat pada model yang benar-benar dipanggil.

    `bind_tools` mengembalikan salinan berlabel. Log panggilan dipakai bersama semua salinan,
    jadi test bisa melihat model mana (tanpa tool, atau dengan tool apa) yang dipakai per giliran.
    """

    _label: tuple[str, ...] = PrivateAttr(default=())
    _calls: list[tuple[tuple[str, ...], list[BaseMessage]]] = PrivateAttr(default_factory=list)

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],  # Any: API induk
        *,
        tool_choice: str | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> Runnable[LanguageModelInput, AIMessage]:
        bound = self.model_copy()
        bound._label = tuple(getattr(item, "name", str(item)) for item in tools)
        bound._calls = self._calls
        return bound

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> ChatResult:
        self._calls.append((self._label, list(messages)))
        return super()._generate(messages, stop, run_manager, **kwargs)

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> Iterator[ChatGenerationChunk]:
        self._calls.append((self._label, list(messages)))
        yield from super()._stream(messages, stop, run_manager, **kwargs)

    @property
    def tools_per_call(self) -> list[tuple[str, ...]]:
        return [label for label, _ in self._calls]

    def prompt(self, call_index: int) -> str:
        return str(self._calls[call_index][1][0].content)


def load_skill_call(name: str, path: str | None = None) -> AIMessage:
    args: dict[str, str] = {"name": name}
    if path is not None:
        args["path"] = path
    return AIMessage(content="", tool_calls=[{"name": "load_skill", "args": args, "id": "s1"}])


def run_config(*skill_ids: str) -> RunnableConfig:
    configurable: dict[str, Any] = {"thread_id": "t1"}  # Any: nilai configurable
    if skill_ids:
        configurable["project_skill_ids"] = list(skill_ids)
    return RunnableConfig(configurable=configurable)


@pytest.fixture
async def toolkit() -> SkillToolkit:
    registry = SkillRegistry([FilesystemSkillSource(BUILTIN_SKILLS_DIR)])
    await registry.load()
    return SkillToolkit(registry)


async def ask(
    agent: ToolCallingAgent, model: FakeModel, config: RunnableConfig
) -> list[BaseMessage]:
    graph = agent.build(model, InMemorySaver())
    result = await graph.ainvoke({"messages": [HumanMessage("Ringkas rapat tadi.")]}, config)
    return result["messages"]


async def test_chatbot_loads_active_skill_and_receives_its_content(toolkit: SkillToolkit) -> None:
    model = BindingRecorder(responses=[load_skill_call("meeting-notes"), "## Summary\n..."])

    messages = await ask(ChatbotAgent(skills=toolkit), model, run_config(NOTES))

    tool_result = messages[2]
    assert isinstance(tool_result, ToolMessage)
    assert str(tool_result.content).startswith("# Meeting notes")
    assert messages[-1].content == "## Summary\n..."
    assert model.tools_per_call[0] == ("load_skill",)
    assert "- meeting-notes: Turns a meeting transcript" in model.prompt(0)


async def test_inactive_skill_returns_tool_error_not_content(toolkit: SkillToolkit) -> None:
    model = BindingRecorder(responses=[load_skill_call("research-report"), "Maaf."])

    messages = await ask(ChatbotAgent(skills=toolkit), model, run_config(NOTES))

    tool_result = messages[2]
    assert isinstance(tool_result, ToolMessage)
    assert tool_result.status == "error"
    assert "not available in this project" in str(tool_result.content)
    assert "Research report" not in str(tool_result.content)


async def test_skill_resource_is_loaded_by_path(toolkit: SkillToolkit) -> None:
    research = create_research_assistant(skills=toolkit)
    model = BindingRecorder(
        responses=[
            load_skill_call("research-report", "references/report-template.md"),
            "Laporan.",
        ]
    )

    messages = await ask(research, model, run_config(REPORT))

    assert str(messages[2].content).startswith("# Report template")


async def test_no_tools_are_bound_without_active_skills(toolkit: SkillToolkit) -> None:
    model = BindingRecorder(responses=["Halo"])
    agent = ChatbotAgent(skills=toolkit)

    await ask(agent, model, run_config())

    assert model.tools_per_call == [()]
    assert "## Skills" not in model.prompt(0)


async def test_research_assistant_binds_skill_tool_only_with_active_skills(
    toolkit: SkillToolkit,
) -> None:
    model = BindingRecorder(responses=["A", "B"])
    graph = create_research_assistant(skills=toolkit).build(model, InMemorySaver())

    await graph.ainvoke({"messages": [HumanMessage("a")]}, run_config())
    await graph.ainvoke({"messages": [HumanMessage("b")]}, run_config(REPORT))

    assert model.tools_per_call == [
        ("web_search", "calculator"),
        ("web_search", "calculator", "load_skill"),
    ]


async def test_chatbot_without_toolkit_has_no_tools_at_all() -> None:
    model = BindingRecorder(responses=["Halo"])

    await ask(ChatbotAgent(), model, run_config(NOTES))

    assert model.tools_per_call == [()]
    assert "## Skills" not in model.prompt(0)
