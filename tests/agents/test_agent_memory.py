"""Agent memakai long-term memory user dengan persetujuan (F30, FR-40, NFR-9)."""

from collections.abc import Callable, Sequence
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command
from pydantic import PrivateAttr

from agent_service.agents.base import AgentGraph
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.agents.research import create_research_assistant
from agent_service.harness.context import MEMORY_TITLE
from agent_service.llm.fake import FakeModel
from agent_service.memory import user_memories
from agent_service.memory.user_memories import UserMemoryRepository

MEMORY_HEADING = f"## {MEMORY_TITLE}"
PREFERENCE = "User prefers green tea"


def save_call(memory: str = PREFERENCE, call_id: str = "save1") -> dict[str, Any]:
    return {"name": "save_memory", "args": {"memory": memory}, "id": call_id}


SAVE_REPLY = AIMessage(content="", tool_calls=[save_call()])


class RecordingModel(FakeModel):
    """FakeModel yang mencatat tool yang di-bind dan input setiap panggilan."""

    _bound: list[list[str]] = PrivateAttr(default_factory=list)
    _inputs: list[list[BaseMessage]] = PrivateAttr(default_factory=list)

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],  # Any: API induk
        *,
        tool_choice: str | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> Runnable[LanguageModelInput, AIMessage]:
        self._bound.append([tool.name for tool in tools if isinstance(tool, BaseTool)])
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> ChatResult:
        self._inputs.append(list(messages))
        return super()._generate(messages, stop, run_manager, **kwargs)

    @property
    def bound(self) -> list[list[str]]:
        return self._bound

    @property
    def last_prompt(self) -> str:
        return self._inputs[-1][0].text


def run_config(thread_id: str, user_id: str = "alice") -> RunnableConfig:
    return RunnableConfig(configurable={"thread_id": thread_id, "user_id": user_id})


def user_turn(text: str) -> dict[str, list[HumanMessage]]:
    return {"messages": [HumanMessage(text)]}


async def saved_texts(store: InMemoryStore, user_id: str = "alice") -> list[str]:
    records = await UserMemoryRepository(store).list_memories(user_id)
    return [record.text for record in records]


def chatbot(model: FakeModel, store: InMemoryStore | None) -> AgentGraph:
    return ChatbotAgent(use_memory=True).build(model, InMemorySaver(), store)


async def test_memory_is_saved_after_approval_and_used_in_another_thread() -> None:
    store = InMemoryStore()
    model = RecordingModel(responses=[SAVE_REPLY, "Noted.", "Hello again."])
    graph = chatbot(model, store)

    asked = await graph.ainvoke(user_turn("Remember that I like green tea"), run_config("t1"))
    [question] = asked["__interrupt__"]
    stored_before_approval = await saved_texts(store)
    await graph.ainvoke(Command(resume="yes"), run_config("t1"))
    await graph.ainvoke(user_turn("Hi"), run_config("t2"))

    assert PREFERENCE in question.value
    assert stored_before_approval == []
    assert await saved_texts(store) == [PREFERENCE]
    assert f"{MEMORY_HEADING}\n" in model.last_prompt
    assert f"- {PREFERENCE}" in model.last_prompt


async def test_declined_memory_is_not_saved_and_reply_reaches_the_model() -> None:
    store = InMemoryStore()
    graph = chatbot(RecordingModel(responses=[SAVE_REPLY, "Okay, I won't."]), store)

    await graph.ainvoke(user_turn("I like green tea"), run_config("t1"))
    result = await graph.ainvoke(Command(resume="no, keep that private"), run_config("t1"))

    [tool_result] = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert "did not approve" in tool_result.text
    assert "no, keep that private" in tool_result.text
    assert await saved_texts(store) == []
    assert result["messages"][-1].text == "Okay, I won't."


async def test_memories_of_one_user_never_reach_another_user() -> None:
    store = InMemoryStore()
    await UserMemoryRepository(store).save("alice", "Alice's secret project is Apollo")
    model = RecordingModel(responses=["Hi Bob."])
    graph = chatbot(model, store)

    await graph.ainvoke(user_turn("What do you know about me?"), run_config("b1", "bob"))

    assert MEMORY_HEADING not in model.last_prompt
    assert "Apollo" not in model.last_prompt


async def test_two_saves_in_one_turn_ask_twice_without_duplicates() -> None:
    store = InMemoryStore()
    both = AIMessage(
        content="", tool_calls=[save_call("Likes tea", "s1"), save_call("Is a nurse", "s2")]
    )
    graph = chatbot(RecordingModel(responses=[both, "Saved both."]), store)

    first = await graph.ainvoke(user_turn("I like tea and I'm a nurse"), run_config("t1"))
    second = await graph.ainvoke(Command(resume="yes"), run_config("t1"))
    await graph.ainvoke(Command(resume="ya"), run_config("t1"))

    assert "Likes tea" in first["__interrupt__"][0].value
    assert "Is a nurse" in second["__interrupt__"][0].value
    assert sorted(await saved_texts(store)) == ["Is a nurse", "Likes tea"]


async def test_full_memory_is_reported_to_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(user_memories, "MAX_MEMORIES_PER_USER", 1)
    store = InMemoryStore()
    await UserMemoryRepository(store).save("alice", "Existing fact")
    graph = chatbot(RecordingModel(responses=[SAVE_REPLY, "Memory is full."]), store)

    await graph.ainvoke(user_turn("Remember I like green tea"), run_config("t1"))
    result = await graph.ainvoke(Command(resume="yes"), run_config("t1"))

    [tool_result] = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_result.status == "error"
    assert "Delete some first" in tool_result.text
    assert await saved_texts(store) == ["Existing fact"]


async def test_without_store_the_chatbot_has_no_memory_tools() -> None:
    model = RecordingModel(responses=["Hi."])
    graph = chatbot(model, None)

    await graph.ainvoke(user_turn("Hi"), run_config("t1"))

    assert model.bound == []
    assert MEMORY_HEADING not in model.last_prompt


async def test_memory_needs_opt_in_even_with_a_store() -> None:
    model = RecordingModel(responses=["Hi."])

    ChatbotAgent().build(model, InMemorySaver(), InMemoryStore())

    assert model.bound == []


def test_research_assistant_binds_memory_next_to_its_tools() -> None:
    model = RecordingModel()

    create_research_assistant(use_memory=True).build(model, InMemorySaver(), InMemoryStore())

    assert model.bound[0] == ["web_search", "calculator", "search_memory", "save_memory"]
