"""Model response API: message chat, riwayat, thread, dan metadata service.

>>> ChatMessage(type="ai", content="Halo!").tool_calls
[]
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, JsonValue

MessageType = Literal["human", "ai", "tool", "custom"]


class ToolCall(BaseModel):
    """Permintaan model untuk memanggil satu tool."""

    name: str = Field(examples=["calculator"])
    args: dict[str, JsonValue] = Field(default_factory=dict, examples=[{"expression": "12 * 7"}])
    id: str | None = Field(default=None, description="ID dari provider, dipakai oleh ToolMessage.")


class ChatMessage(BaseModel):
    """Satu message dalam percakapan, dalam bentuk netral (bukan objek LangChain)."""

    type: MessageType = Field(description="Peran message.")
    content: str = Field(examples=["Hasilnya 84."])
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = Field(
        default=None,
        description="Untuk message `tool`: ID tool call yang dijawab.",
    )
    run_id: str | None = Field(default=None, description="ID run agent yang menghasilkan message.")
    agent: str | None = Field(
        default=None,
        description="Sub-agent (expert) yang membuat message ini, atau kosong untuk agent utama.",
    )
    reasoning: str | None = Field(
        default=None,
        description="Untuk message `ai`: pemikiran model sebelum menjawab, jika model mengirimnya.",
    )
    response_metadata: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Metadata dari provider, misalnya jumlah token.",
    )
    custom_data: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Payload untuk message `custom` (event khusus agent).",
    )


class ChatHistory(BaseModel):
    """Seluruh message dalam satu thread, urut kronologis."""

    messages: list[ChatMessage]


class ThreadSummary(BaseModel):
    """Ringkasan satu thread untuk daftar riwayat percakapan."""

    thread_id: str
    agent_id: str = Field(description="Agent yang menjalankan thread ini.")
    title: str = Field(description="Judul custom (jika di-rename) atau dari pesan human pertama.")
    updated_at: datetime | None = Field(default=None, description="Waktu checkpoint terakhir.")


class UserThreads(BaseModel):
    """Daftar thread milik satu user, terbaru lebih dulu."""

    threads: list[ThreadSummary]


class AgentInfo(BaseModel):
    """Informasi publik satu agent."""

    key: str = Field(examples=["research-assistant"])
    description: str
    config_schema: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="JSON Schema untuk `agent_config` agent ini.",
    )


class ServiceMetadata(BaseModel):
    """Isi endpoint `/info`: agent dan model yang tersedia."""

    agents: list[AgentInfo]
    models: list[str]
    default_agent: str
    default_model: str


class HealthStatus(BaseModel):
    """Isi endpoint `/health`.

    >>> HealthStatus().model_dump()
    {'status': 'ok'}
    """

    status: Literal["ok"] = "ok"


if __name__ == "__main__":
    reply = ChatMessage(
        type="ai",
        content="",
        tool_calls=[ToolCall(name="calculator", args={"expression": "12 * 7"}, id="call-1")],
    )
    print(ChatHistory(messages=[ChatMessage(type="human", content="12 * 7?"), reply]))
