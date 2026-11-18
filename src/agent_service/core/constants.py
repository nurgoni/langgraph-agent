"""Konstanta bernama yang dipakai lintas layer.

Setiap literal yang punya makna ditaruh di sini, bukan diulang inline.

>>> DEFAULT_PORT
8080
>>> MIN_PORT <= DEFAULT_PORT <= MAX_PORT
True
"""

from pathlib import Path
from typing import Final, Literal

ENV_FILE: Final = Path(".env")
ENV_FILE_ENCODING: Final = "utf-8"

DEFAULT_HOST: Final = "0.0.0.0"
DEFAULT_PORT: Final = 8080
MIN_PORT: Final = 1
MAX_PORT: Final = 65535

# Kredensial dev, sama dengan service `postgres` di compose.yaml (keputusan user, F23).
# 127.0.0.1, bukan localhost: di Docker Desktop Windows koneksi ke ::1 menggantung sampai timeout.
DEFAULT_DATABASE_URL: Final = "postgresql://agent:agent@127.0.0.1:5432/agent_service"
POSTGRES_URL_SCHEMES: Final = ("postgresql", "postgres")

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
DEFAULT_LOG_LEVEL: Final[LogLevel] = "INFO"

FAKE_MODEL_NAME: Final = "fake"
# Pemisah untuk env var berisi daftar, seperti AVAILABLE_MODELS dan CORS_ORIGINS.
LIST_SEPARATOR: Final = ","

# Pemilik run (`sub` token), diisi service di `configurable` setiap run. Dibaca harness untuk
# memilih namespace memory user (FR-40).
USER_ID_CONFIG_KEY: Final = "user_id"

# Kunci `configurable` yang diisi service untuk run di dalam project (FR-36), dibaca agent dan
# harness (F27/F28). Sama dengan kunci reservasi di `schema/requests.py`.
PROJECT_ID_CONFIG_KEY: Final = "project_id"
PROJECT_INSTRUCTIONS_CONFIG_KEY: Final = "project_instructions"
PROJECT_SKILL_IDS_CONFIG_KEY: Final = "project_skill_ids"

# Auth per user (FR-33). Token tanpa refresh token, cukup untuk satu hari demo (keputusan user).
SECONDS_PER_HOUR: Final = 3600
DEFAULT_JWT_TTL_HOURS: Final = 12
DEFAULT_JWT_TTL_SECONDS: Final = DEFAULT_JWT_TTL_HOURS * SECONDS_PER_HOUR
MIN_JWT_TTL_SECONDS: Final = 60
# 32 byte = 256 bit, sama dengan ukuran output HMAC-SHA256 yang dipakai HS256.
MIN_JWT_SECRET_LENGTH: Final = 32

# Batas token jawaban per panggilan model (FR-30). Di Ollama token reasoning ikut dihitung.
# qwen3.5:9b terukur 442–3265 token per jawaban, jadi 8192 memberi ruang ±2,5 kali.
DEFAULT_LLM_MAX_TOKENS: Final = 8192
MIN_LLM_MAX_TOKENS: Final = 1

# Nama parameter batas token di body request. Ollama/vLLM/llama.cpp hanya membaca `max_tokens`,
# sedangkan model reasoning OpenAI (gpt-5, o-series) hanya menerima `max_completion_tokens`.
MaxTokensParam = Literal["max_tokens", "max_completion_tokens"]
DEFAULT_LLM_MAX_TOKENS_PARAM: Final[MaxTokensParam] = "max_tokens"

# Anggaran token riwayat + ringkasan per panggilan model (FR-39, keputusan user F29). qwen3.5:9b
# di Ollama terukur membaca prompt ±35k token tanpa pemotongan, dan 16k menjaga giliran tetap
# cepat di model lokal. Batas bawah memberi ruang untuk ringkasan dan satu giliran pendek.
DEFAULT_CONTEXT_MAX_TOKENS: Final = 16000
MIN_CONTEXT_MAX_TOKENS: Final = 1000

# Tag run model yang token/reasoning-nya tidak dialirkan ke chat (ekstraksi, peringkasan).
SKIP_STREAM_TAG: Final = "skip_stream"

# Artifact (FR-46, keputusan user F35). Direktori relatif terhadap folder kerja service; image
# service me-mount volume di `/app/data/artifacts`.
DEFAULT_ARTIFACT_DIR: Final = Path("data/artifacts")
BYTES_PER_MEGABYTE: Final = 1024 * 1024
DEFAULT_ARTIFACT_MAX_MEGABYTES: Final = 25
DEFAULT_ARTIFACT_MAX_BYTES: Final = DEFAULT_ARTIFACT_MAX_MEGABYTES * BYTES_PER_MEGABYTE
MIN_ARTIFACT_MAX_BYTES: Final = 1
# Kunci `additional_kwargs` message LangChain yang berisi referensi artifact (pola penanda F17).
ARTIFACTS_KWARG: Final = "artifacts"

# Batas output tool sebelum dipindah ke workspace (FR-48, keputusan user F36): ±25% anggaran riwayat
# default, jadi hasil web search biasa tetap utuh.
DEFAULT_TOOL_OUTPUT_MAX_TOKENS: Final = 4000
MIN_TOOL_OUTPUT_MAX_TOKENS: Final = 100
# Kunci `additional_kwargs` message human berisi path lampiran di workspace thread (F36).
WORKSPACE_FILES_KWARG: Final = "workspace_files"

# Sandbox eksekusi kode (FR-49, keputusan user F37). Batas waktu per eksekusi; batas lain
# (memori, CPU, jumlah proses) ditetapkan runner.
DEFAULT_SANDBOX_TIMEOUT_SECONDS: Final = 60
MIN_SANDBOX_TIMEOUT_SECONDS: Final = 1
MAX_SANDBOX_TIMEOUT_SECONDS: Final = 600
# Kunci `configurable`: persetujuan sebelum eksekusi kode di project (`ProjectSettings`).
PROJECT_TOOL_APPROVAL_CONFIG_KEY: Final = "project_tool_approval"
