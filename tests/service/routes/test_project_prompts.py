"""Instruksi project sampai ke system prompt model lewat route project (F27, FR-37)."""

from typing import Any

import pytest
from httpx import AsyncClient
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.outputs import ChatResult
from pydantic import PrivateAttr

from agent_service.agents.base import AgentGraph, BaseAgent, Checkpointer
from agent_service.agents.chatbot import ChatbotAgent
from agent_service.llm.fake import FakeModel


class PromptRecorder(FakeModel):
    """FakeModel yang merekam message yang diterima di setiap panggilan."""

    _seen: list[list[BaseMessage]] = PrivateAttr(default_factory=list)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # Any: API induk
    ) -> ChatResult:
        self._seen.append(list(messages))
        return super()._generate(messages, stop, run_manager, **kwargs)

    def system_prompts(self) -> list[str]:
        prompts: list[str] = []
        for messages in self._seen:
            if isinstance(messages[0], SystemMessage):
                prompts.append(str(messages[0].content))
        return prompts


class RecordedChatbot(ChatbotAgent):
    """Chatbot asli (dengan ContextBuilder) yang memakai satu model perekam."""

    def __init__(self, recorder: PromptRecorder) -> None:
        super().__init__()
        self._recorder = recorder

    def build(self, model: BaseChatModel, checkpointer: Checkpointer) -> AgentGraph:
        return super().build(self._recorder, checkpointer)


@pytest.fixture
def recorder() -> PromptRecorder:
    return PromptRecorder()


@pytest.fixture
def agents(recorder: PromptRecorder) -> list[BaseAgent]:
    return [RecordedChatbot(recorder)]


async def test_project_instructions_reach_the_model_and_updates_apply_next_turn(
    client: AsyncClient, recorder: PromptRecorder
) -> None:
    created = await client.post(
        "/projects",
        json={"name": "Notulen", "base_agent_id": "chatbot", "instructions": "Pakai poin."},
    )
    project_id = created.json()["id"]

    await client.post(f"/projects/{project_id}/invoke", json={"message": "a", "thread_id": "t1"})
    await client.patch(f"/projects/{project_id}", json={"instructions": "Pakai tabel."})
    await client.post(f"/projects/{project_id}/invoke", json={"message": "b", "thread_id": "t1"})

    first, second = recorder.system_prompts()
    assert "## Project instructions\nPakai poin." in first
    assert "## Project instructions\nPakai tabel." in second


async def test_agent_route_prompt_has_no_project_section(
    client: AsyncClient, recorder: PromptRecorder
) -> None:
    await client.post("/chatbot/invoke", json={"message": "Halo"})

    [prompt] = recorder.system_prompts()
    assert "## Project instructions" not in prompt
    assert prompt.startswith("## Environment\nCurrent date:")


async def test_builtin_project_instructions_are_used(
    client: AsyncClient, recorder: PromptRecorder
) -> None:
    await client.post("/projects/general-assistant/invoke", json={"message": "Halo"})

    [prompt] = recorder.system_prompts()
    assert "Keep answers concise." in prompt
