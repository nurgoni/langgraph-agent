"""Registry agent: pendaftaran, pemuatan saat startup, dan cache graph per model."""

import logging

from langgraph.store.base import BaseStore

from agent_service.agents.base import AgentGraph, BaseAgent, Checkpointer
from agent_service.agents.errors import (
    AgentNotFoundError,
    AgentUnavailableError,
    DuplicateAgentError,
)
from agent_service.llm.factory import ModelFactory

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Menyimpan agent per `agent_id` dan graph hasil compile per pasangan agent + model.

    Dibuat di lifespan service, bukan saat import. Alurnya: `register` semua agent, lalu
    `await load_all()`. Agent yang gagal dimuat ditandai unavailable, tanpa menghentikan agent lain.

    >>> import asyncio
    >>> from langgraph.checkpoint.memory import InMemorySaver
    >>> from agent_service.agents.chatbot import ChatbotAgent
    >>> from agent_service.core.settings import Settings
    >>> factory = ModelFactory(Settings(_env_file=None, use_fake_model=True, jwt_secret="x" * 32))
    >>> registry = AgentRegistry(factory, InMemorySaver())
    >>> registry.register(ChatbotAgent())
    >>> asyncio.run(registry.load_all())
    >>> registry.is_available("chatbot")
    True
    """

    def __init__(
        self,
        model_factory: ModelFactory,
        checkpointer: Checkpointer,
        store: BaseStore | None = None,
    ) -> None:
        """Inisialisasi registry kosong.

        Args:
            model_factory: Sumber chat model untuk setiap graph.
            checkpointer: Saver yang dipakai semua graph.
            store: Store long-term memory untuk agent yang memakainya. `None` berarti semua
                graph dibangun tanpa memory.
        """
        self._model_factory = model_factory
        self._checkpointer = checkpointer
        self._store = store
        self._agents: dict[str, BaseAgent] = {}
        self._available: set[str] = set()
        self._graphs: dict[tuple[str, str, int], AgentGraph] = {}

    def register(self, agent: BaseAgent) -> None:
        """Daftarkan agent. Agent belum bisa dipakai sebelum `load_all` dipanggil.

        Raises:
            DuplicateAgentError: Jika `agent.agent_id` sudah terdaftar.
        """
        if agent.agent_id in self._agents:
            raise DuplicateAgentError(agent.agent_id)
        self._agents[agent.agent_id] = agent

    async def load_all(self) -> None:
        """Muat setiap agent yang belum tersedia, lalu compile graph untuk model default (FR-3)."""
        for agent in self._agents.values():
            if agent.agent_id not in self._available:
                await self._load(agent)

    def get_agent(self, agent_id: str) -> BaseAgent:
        """Ambil agent terdaftar, misalnya untuk memvalidasi `agent_config`.

        Raises:
            AgentNotFoundError: Jika `agent_id` tidak terdaftar.
        """
        agent = self._agents.get(agent_id)
        if agent is None:
            raise AgentNotFoundError(agent_id)
        return agent

    def get_graph(
        self, agent_id: str, model_name: str | None = None, max_tokens: int | None = None
    ) -> AgentGraph:
        """Ambil graph untuk agent, model, dan batas token, di-compile sekali lalu di-reuse.

        Args:
            agent_id: ID agent dari URL atau dari project.
            model_name: Model dari request atau project. `None` berarti `DEFAULT_MODEL`.
            max_tokens: Batas token dari project (FR-30). `None` berarti `LLM_MAX_TOKENS`.

        Returns:
            Graph yang sudah di-compile dengan checkpointer registry.

        Raises:
            AgentNotFoundError: Jika `agent_id` tidak terdaftar.
            AgentUnavailableError: Jika agent belum dimuat atau gagal dimuat.
            UnknownModelError: Jika model tidak ada di allowlist.
        """
        agent = self.get_agent(agent_id)
        if agent_id not in self._available:
            raise AgentUnavailableError(agent_id)
        return self._get_or_build_graph(agent, model_name, max_tokens)

    def is_available(self, agent_id: str) -> bool:
        """Cek apakah agent sudah dimuat dan siap dipakai."""
        return agent_id in self._available

    def list_agents(self) -> list[BaseAgent]:
        """Semua agent terdaftar, urut sesuai pendaftaran."""
        return list(self._agents.values())

    async def _load(self, agent: BaseAgent) -> None:
        """Jalankan `load()` dan compile graph default. Kegagalan hanya dicatat di log."""
        try:
            await agent.load()
            self._get_or_build_graph(agent, None, None)
        # Batas sistem: agent bisa bergantung pada resource eksternal apa pun (MCP, API). Satu
        # agent yang gagal tidak boleh menghentikan startup service (FR-3).
        except Exception:
            logger.exception("Agent %r failed to load and is marked unavailable", agent.agent_id)
            return
        self._available.add(agent.agent_id)
        logger.info("Agent %r loaded", agent.agent_id)

    def _get_or_build_graph(
        self, agent: BaseAgent, model_name: str | None, max_tokens: int | None
    ) -> AgentGraph:
        """Ambil graph dari cache atau compile graph baru, tanpa cek ketersediaan agent."""
        resolved_name = self._model_factory.resolve_name(model_name)
        token_limit = self._model_factory.resolve_max_tokens(max_tokens)
        key = (agent.agent_id, resolved_name, token_limit)
        graph = self._graphs.get(key)
        if graph is None:
            model = self._model_factory.create(resolved_name, token_limit)
            graph = agent.build(model, self._checkpointer, self._store)
            self._graphs[key] = graph
        return graph
