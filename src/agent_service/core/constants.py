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
