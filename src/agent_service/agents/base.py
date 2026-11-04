"""Kontrak agent: identitas, schema config, dan cara membangun graph.

>>> EmptyAgentConfig.model_validate({})
EmptyAgentConfig()
>>> EmptyAgentConfig.model_json_schema()["description"]
'This agent accepts no configuration options.'
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Final

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict, JsonValue

EMPTY_CONFIG_DESCRIPTION: Final = "This agent accepts no configuration options."

# Any: tipe state, context, input, dan output berbeda di setiap agent.
type AgentGraph = CompiledStateGraph[Any, Any, Any, Any]
# Any: tipe versi channel bergantung pada implementasi saver.
type Checkpointer = BaseCheckpointSaver[Any]


class EmptyAgentConfig(BaseModel):
    """Config default untuk agent tanpa opsi: key apa pun ditolak.

    Docstring `config_schema` menjadi `description` di JSON Schema publik (`/info`), jadi
    deskripsi publiknya ditulis eksplisit dalam bahasa Inggris.
    """

    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"description": EMPTY_CONFIG_DESCRIPTION}
    )


class BaseAgent(ABC):
    """Agent yang bisa didaftarkan di `AgentRegistry`.

    Subclass wajib mengimplementasikan `build`. Override `load` jika agent butuh inisialisasi
    async (misalnya koneksi MCP), dan ganti `config_schema` jika agent menerima `agent_config`.
    Satu instance agent bisa membangun beberapa graph, satu per model.
    """

    config_schema: ClassVar[type[BaseModel]] = EmptyAgentConfig

    def __init__(self, agent_id: str, description: str) -> None:
        """Inisialisasi identitas agent.

        Args:
            agent_id: ID unik yang dipakai di URL (`/{agent_id}/invoke`).
            description: Deskripsi singkat untuk `/info`.
        """
        self.agent_id = agent_id
        self.description = description

    async def load(self) -> None:  # noqa: B027 - hook opsional, sengaja tidak abstract
        """Siapkan resource async sebelum `build` dipanggil. Default-nya tidak melakukan apa-apa."""

    @abstractmethod
    def build(self, model: BaseChatModel, checkpointer: Checkpointer) -> AgentGraph:
        """Bangun dan compile graph agent.

        Args:
            model: Chat model yang dipilih untuk request (FR-4).
            checkpointer: Saver yang diberikan ke `compile(checkpointer=...)`.

        Returns:
            Graph yang sudah di-compile dengan checkpointer.
        """

    def parse_config(self, raw_config: dict[str, JsonValue]) -> BaseModel:
        """Validasi `agent_config` dari request terhadap `config_schema`.

        Args:
            raw_config: Isi `agent_config` dari request.

        Returns:
            Instance `config_schema` yang sudah tervalidasi.

        Raises:
            pydantic.ValidationError: Jika ada key yang tidak dikenal atau nilai tidak valid.
        """
        return self.config_schema.model_validate(raw_config)

    def __repr__(self) -> str:
        """Representasi ringkas untuk log."""
        return f"{type(self).__name__}(agent_id={self.agent_id!r})"
