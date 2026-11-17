"""Agent menerapkan `ContextPolicy` sebelum setiap panggilan model (F29, FR-39)."""

from collections.abc import Iterator
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import PrivateAttr

from agent_service.agents.chatbot import ChatbotAgent
from agent_service.agents.research import create_research_assistant
from agent_service.agents.supervisor import create_supervisor_agent
from agent_service.agents.tools.web_search import SearchResult
from agent_service.harness.context import SUMMARY_TITLE
from agent_service.harness.context_policy import SUMMARY_PROMPT, ContextPolicy
from agent_service.llm.fake import FakeModel

BUDGET = 600
SUMMARY_TEXT = "Earlier: the user asked many long questions."
LONG_QUESTION = "Please explain this topic in detail. " * 12  # ±110 token
SUMMARY_MARKER = SUMMARY_PROMPT.split("\n", maxsplit=1)[0]


class ConversationModel(FakeModel):
    """Membalas permintaan ringkasan dengan `SUMMARY_TEXT`, dan mencatat input percakapan."""

    _chat_inputs: list[list[BaseMessage]] = PrivateAttr(default_factory=list)
    _summary_calls: int = PrivateAttr(default=0)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> ChatResult:
        if messages[0].text.startswith(SUMMARY_MARKER):
            self._summary_calls += 1
            reply = AIMessage(content=SUMMARY_TEXT)
            return ChatResult(generations=[ChatGeneration(message=reply)])
        self._chat_inputs.append(list(messages))
        return super()._generate(messages, stop, run_manager, **kwargs)

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> Iterator[ChatGenerationChunk]:
        result = self._generate(messages, stop, run_manager, **kwargs)
        generation: ChatGeneration = result.generations[0]
        yield ChatGenerationChunk(message=generation.message)  # pyrefly: ignore[bad-argument-type]

    @property
    def chat_inputs(self) -> list[list[BaseMessage]]:
        return self._chat_inputs

    @property
    def summary_calls(self) -> int:
        return self._summary_calls


class FakeSearch:
    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        return [SearchResult("Result", "https://example.com", "snippet " * 60)]


def config() -> RunnableConfig:
    return RunnableConfig(configurable={"thread_id": "long"})


def history_tokens(policy: ContextPolicy, model_input: list[BaseMessage]) -> int:
    """Token riwayat yang dikirim ke model, tanpa system prompt (message pertama)."""
    return policy.tokens(model_input[1:])


async def test_long_chatbot_thread_stays_under_budget_and_keeps_full_history() -> None:
    policy = ContextPolicy(max_tokens=BUDGET)
    model = ConversationModel(responses=["Short answer."])
    graph = ChatbotAgent(context_policy=policy).build(model, InMemorySaver())

    for turn in range(12):
        await graph.ainvoke({"messages": [HumanMessage(f"{turn} {LONG_QUESTION}")]}, config())

    state = (await graph.aget_state(config())).values
    assert len(state["messages"]) == 24
    assert state["summary"] == SUMMARY_TEXT
    assert model.summary_calls >= 1
    for model_input in model.chat_inputs:
        assert history_tokens(policy, model_input) + policy.tokens([], SUMMARY_TEXT) <= BUDGET
    last_prompt = model.chat_inputs[-1][0].text
    assert f"## {SUMMARY_TITLE}\n{SUMMARY_TEXT}" in last_prompt
    assert all(message.text != SUMMARY_TEXT for message in state["messages"])


async def test_short_thread_is_sent_whole_without_summary() -> None:
    model = ConversationModel(responses=["Hi."])
    graph = ChatbotAgent().build(model, InMemorySaver())

    await graph.ainvoke({"messages": [HumanMessage("Halo")]}, config())
    await graph.ainvoke({"messages": [HumanMessage("Lagi")]}, config())

    assert model.summary_calls == 0
    assert [m.text for m in model.chat_inputs[-1][1:]] == ["Halo", "Hi.", "Lagi"]
    assert SUMMARY_TITLE not in model.chat_inputs[-1][0].text


async def test_research_assistant_never_splits_tool_calls() -> None:
    policy = ContextPolicy(max_tokens=BUDGET)
    search = AIMessage(
        content="",
        tool_calls=[{"name": "web_search", "args": {"query": "x"}, "id": "search"}],
    )
    model = ConversationModel(responses=[search, "Found it."])
    agent = create_research_assistant(FakeSearch(), context_policy=policy)
    graph = agent.build(model, InMemorySaver())

    for turn in range(8):
        await graph.ainvoke({"messages": [HumanMessage(f"{turn} {LONG_QUESTION}")]}, config())

    assert model.summary_calls >= 1
    for model_input in model.chat_inputs:
        sent = model_input[1:]
        assert not isinstance(sent[0], ToolMessage)
        tool_results = [message for message in sent if isinstance(message, ToolMessage)]
        calls = {call["id"] for m in sent if isinstance(m, AIMessage) for call in m.tool_calls}
        assert {result.tool_call_id for result in tool_results} == calls
        assert history_tokens(policy, model_input) <= BUDGET


async def test_supervisor_applies_the_policy_to_its_own_view() -> None:
    policy = ContextPolicy(max_tokens=BUDGET)
    model = ConversationModel(responses=["Done."])
    graph = create_supervisor_agent(context_policy=policy).build(model, InMemorySaver())

    for turn in range(12):
        await graph.ainvoke({"messages": [HumanMessage(f"{turn} {LONG_QUESTION}")]}, config())

    state = (await graph.aget_state(config())).values
    assert len(state["messages"]) == 24
    assert state["summary"] == SUMMARY_TEXT
    assert all(history_tokens(policy, model_input) <= BUDGET for model_input in model.chat_inputs)
