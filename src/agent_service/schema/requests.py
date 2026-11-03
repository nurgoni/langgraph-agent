"""Model request API (body dan query) yang dipakai bersama service, client, dan UI.

>>> UserInput(message="Halo").agent_config
{}
>>> ChatHistoryInput(thread_id="t-1", user_id="u-1").thread_id
't-1'
"""

from typing import Annotated, Final

from pydantic import BaseModel, Field, JsonValue, StringConstraints, field_validator

RESERVED_AGENT_CONFIG_KEYS: Final = frozenset({"thread_id", "user_id", "model"})

THREADS_LIMIT_DEFAULT: Final = 20
THREADS_LIMIT_MIN: Final = 1
THREADS_LIMIT_MAX: Final = 100
TITLE_MAX_LENGTH: Final = 60

ThreadTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX_LENGTH),
]


class UserInput(BaseModel):
    """Input user untuk satu run agent (`/invoke`)."""

    message: str = Field(
        min_length=1,
        description="Pesan user, atau jawaban untuk agent yang sedang interrupt.",
        examples=["Berapa 12 * 7?"],
    )
    model: str | None = Field(
        default=None,
        description="Nama model dari allowlist. Kosong berarti memakai model default service.",
        examples=["gpt-5-mini"],
    )
    thread_id: str | None = Field(
        default=None,
        description="Thread yang dilanjutkan. Kosong berarti thread baru.",
    )
    user_id: str | None = Field(
        default=None,
        description="Pemilik thread. Kosong berarti user baru.",
    )
    agent_config: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Konfigurasi khusus agent, divalidasi dengan config_schema milik agent.",
        examples=[{"temperature": 0.2}],
    )

    @field_validator("agent_config")
    @classmethod
    def _reject_reserved_keys(cls, agent_config: dict[str, JsonValue]) -> dict[str, JsonValue]:
        """Tolak key yang sudah diatur service.

        Args:
            agent_config: Config dari request.

        Returns:
            `agent_config` tanpa perubahan.

        Raises:
            ValueError: Jika ada key reservasi (`thread_id`, `user_id`, `model`).
        """
        reserved = sorted(RESERVED_AGENT_CONFIG_KEYS.intersection(agent_config))
        if reserved:
            raise ValueError(f"agent_config must not contain reserved keys: {reserved}")
        return agent_config


class StreamInput(UserInput):
    """Input user untuk `/stream`."""

    stream_tokens: bool = Field(
        default=True,
        description="Kirim token LLM satu per satu, bukan hanya message utuh.",
    )


class ChatHistoryInput(BaseModel):
    """Input untuk membaca riwayat satu thread. Hanya pemilik thread yang boleh membaca."""

    thread_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)


class UserThreadsQuery(BaseModel):
    """Query untuk mendaftar thread milik user."""

    user_id: str = Field(min_length=1)
    limit: int = Field(
        default=THREADS_LIMIT_DEFAULT,
        ge=THREADS_LIMIT_MIN,
        le=THREADS_LIMIT_MAX,
    )


class ThreadRenameInput(BaseModel):
    """Body untuk mengganti judul thread."""

    user_id: str = Field(min_length=1)
    title: ThreadTitle = Field(description="Judul baru. Spasi di awal dan akhir dibuang.")


if __name__ == "__main__":
    print(StreamInput(message="Halo", agent_config={"temperature": 0.2}).model_dump_json())
