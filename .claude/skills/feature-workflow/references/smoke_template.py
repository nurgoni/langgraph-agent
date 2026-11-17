"""Template smoke test dengan model asli di database Postgres sementara.

Salin ke scratchpad, ganti `scenario()`, lalu jalankan:

    uv run python <scratchpad>/smoke_fxx.py

Butuh `docker compose up -d postgres` dan model di `.env` (misalnya Ollama `qwen3.5:9b`). Database
dev tidak disentuh: database `smoke_<acak>` dibuat, dimigrasi, lalu dihapus.
"""

import asyncio
import logging
import time
import uuid
from typing import LiteralString

import psycopg
from httpx import ASGITransport, AsyncClient
from psycopg import sql

from agent_service.core.settings import Settings
from agent_service.memory.migrator import upgrade_database
from agent_service.memory.users import UserRecord
from agent_service.service.app import create_app

SERVER_URL = "postgresql://agent:agent@127.0.0.1:5432/agent_service"
REQUEST_TIMEOUT_SECONDS = 600


def run_admin(template: LiteralString, database_name: str) -> None:
    """`CREATE`/`DROP DATABASE` di server Postgres dev."""
    with psycopg.connect(SERVER_URL, autocommit=True) as connection:
        connection.execute(sql.SQL(template).format(sql.Identifier(database_name)))


async def ask(client: AsyncClient, text: str, thread_id: str | None = None) -> str:
    """Kirim satu pesan, cetak waktu dan potongan jawaban, kembalikan ID thread."""
    started = time.perf_counter()
    response = await client.post("/invoke", json={"message": text, "thread_id": thread_id})
    response.raise_for_status()
    elapsed = time.perf_counter() - started
    print(f"[{elapsed:5.1f}s] {text[:60]!r}\n         -> {response.json()['content'][:300]!r}")
    return response.headers["X-Thread-Id"]


async def scenario(client: AsyncClient) -> None:
    """Ganti dengan skenario fitur. Contoh: dua giliran di thread yang sama."""
    thread_id = await ask(client, "My name is Rani. Just say OK.")
    await ask(client, "What is my name?", thread_id)


async def run(database_url: str) -> None:
    # llm_max_tokens_param: Ollama mengabaikan max_completion_tokens (lihat F21).
    settings = Settings(database_url=database_url, llm_max_tokens_param="max_tokens")
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        user = UserRecord(user_id="smoke", username="smoke", password_hash="", role="user")
        token = app.state.authenticator.issue_token(user).access_token
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as client:
            await scenario(client)


async def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    database_name = f"smoke_{uuid.uuid4().hex[:6]}"
    run_admin("CREATE DATABASE {}", database_name)
    database_url = SERVER_URL.rsplit("/", 1)[0] + "/" + database_name
    try:
        await upgrade_database(database_url)
        await run(database_url)
    finally:
        run_admin("DROP DATABASE IF EXISTS {} WITH (FORCE)", database_name)


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
