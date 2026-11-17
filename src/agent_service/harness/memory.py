"""`MemoryToolkit`: memory user untuk prompt dan tool memory untuk agent (FR-40, ADR 0002).

Dibuat per graph dari store yang diberikan ke `BaseAgent.build`, karena store baru ada setelah
lifespan membuka koneksi Postgres. Memory selalu dibaca dari namespace user pemilik run, jadi
memory user lain tidak pernah masuk prompt (NFR-9).
"""

from typing import Final

from langchain_core.tools import BaseTool
from langgraph.store.base import BaseStore

from agent_service.harness.context import RunConfig
from agent_service.harness.tools.memory import create_memory_tools, memory_user_id, render_memories
from agent_service.memory.user_memories import UserMemoryRepository

# Memory terbaru yang masuk prompt (keputusan user F30). Teksnya juga dibatasi MEMORY_MAX_CHARS
# di ContextBuilder, jadi 20 memory × 500 karakter tetap tidak menggeser bagian lain.
PROMPT_MEMORY_LIMIT: Final = 20
MEMORY_INTRO: Final = (
    "Facts about the user from earlier conversations, saved with their approval (newest "
    "first). Use them when they are relevant, and do not repeat them back unprompted."
)


class MemoryToolkit:
    """Memory terbaru untuk system prompt dan tool `search_memory`/`save_memory`."""

    def __init__(self, store: BaseStore) -> None:
        """Inisialisasi toolkit.

        Args:
            store: Store LangGraph yang dibuka lifespan (`AsyncPostgresStore`).
        """
        self._repository = UserMemoryRepository(store)
        self._tools = create_memory_tools(self._repository)

    @property
    def tools(self) -> list[BaseTool]:
        """Tool memory yang di-bind ke model dan didaftarkan di `ToolNode`."""
        return list(self._tools)

    async def prompt_text(self, config: RunConfig) -> str:
        """Isi bagian `## Memory` untuk run ini, atau string kosong jika user belum punya memory.

        Args:
            config: Config run. User dibaca dari `configurable["user_id"]`.
        """
        user_id = memory_user_id(config)
        if user_id is None:
            return ""
        records = await self._repository.list_memories(user_id, PROMPT_MEMORY_LIMIT)
        if not records:
            return ""
        return f"{MEMORY_INTRO}\n{render_memories(records)}"


if __name__ == "__main__":
    import asyncio

    from langgraph.store.memory import InMemoryStore

    async def _demo() -> None:
        store = InMemoryStore()
        await UserMemoryRepository(store).save("user-1", "User prefers answers in Indonesian")
        toolkit = MemoryToolkit(store)
        print([tool.name for tool in toolkit.tools])
        print(await toolkit.prompt_text({"configurable": {"user_id": "user-1"}}))

    asyncio.run(_demo())
