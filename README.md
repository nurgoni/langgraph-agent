# LangGraph Agent Service

Service untuk menjalankan beberapa agent [LangGraph](https://langchain-ai.github.io/langgraph/)
lewat satu API FastAPI, lengkap dengan streaming SSE, Python client, dan UI chat Streamlit.

Project ini adalah rewrite dari [`agent-service-toolkit/`](agent-service-toolkit/) dengan fokus pada
kode yang sederhana, eksplisit, dan mudah dites (Zen of Python).

> **Status:** v0.1.0 (service) sudah dirilis. M2 selesai di branch fitur: `AgentClient`, UI Streamlit, dan stack Docker Compose dengan test e2e. Rilis v0.2.0 menyusul. Lihat [PRD.md](PRD.md) untuk requirement dan
> [.agents/memory.md](.agents/memory.md) untuk status terkini.

## Fitur

- **Multi-agent registry**: pilih agent lewat URL `/{agent_id}/...`.
- **Streaming SSE**: token dan message (termasuk tool call dan sub-agent) dikirim secara real-time.
- **Reasoning terlihat**: pemikiran model reasoning (misalnya Qwen3 lewat Ollama) di-stream
  sebelum jawaban dan tampil di blok "Thinking" UI.
- **Percakapan persisten**: riwayat thread disimpan di Postgres via LangGraph checkpointer.
- **Human-in-the-loop**: agent bisa berhenti (`interrupt`) dan melanjutkan dengan input user.
- **Python client**: `AgentClient` sync dan async.
- **UI Streamlit**: chat, riwayat thread, pemilih agent dan model.
- **Auth sederhana**: bearer token opsional.

## Arsitektur

```text
┌──────────────┐  HTTP/SSE  ┌──────────────────────────────────────────┐
│ Streamlit UI │ ─────────► │ FastAPI service                          │
│ (ui/)        │            │  router ─► StreamService                 │
└──────┬───────┘            │              │                           │
       │ pakai              │              ▼                           │
┌──────▼───────┐            │  AgentRegistry ─► BaseAgent (graph)      │
│ AgentClient  │            │                     │        │           │
│ (client/)    │            │              ModelFactory  Postgres      │
└──────────────┘            │              (llm/)        checkpointer  │
                            └──────────────────────────────────────────┘
```

## Quickstart

Prasyarat: Python 3.12+, [uv](https://docs.astral.sh/uv/), dan Docker (untuk Postgres).

```bash
# 1. Install dependency (semua extra + tool dev)
uv sync

# 2. Konfigurasi
cp .env.example .env
# isi LLM_BASE_URL, LLM_API_KEY, DEFAULT_MODEL
# atau USE_FAKE_MODEL=true untuk mencoba tanpa API key

# 3. Jalankan Postgres dan siapkan skemanya
docker compose up -d postgres
uv run python -m agent_service.run_migrate

# 4. Jalankan service (http://localhost:8080, docs di /docs)
uv run python -m agent_service.run_service

# 5. Jalankan UI di terminal lain (http://localhost:8501)
uv run streamlit run src/agent_service/ui/app.py
```

Service menolak start jika Postgres tidak terjangkau atau migrasi belum dijalankan, dan pesan
error-nya menyebut perintah yang perlu dijalankan.

UI hanya client: service (langkah 3) harus sudah berjalan di `AGENT_URL`. Jika belum, UI
menampilkan pesan "Cannot reach the agent service at ..." saat pesan dikirim.

**Extras.** Install dasar hanya berisi `schema` + `client` (pydantic, httpx). Komponen lain
dipasang lewat extra:

| Extra | Untuk | Isi utama |
|---|---|---|
| (dasar) | `AgentClient` sebagai library | pydantic, httpx |
| `service` | API FastAPI | fastapi, uvicorn, langgraph, langchain, Postgres (psycopg, SQLAlchemy, Alembic) |
| `ui` | UI Streamlit | streamlit, pydantic-settings |

`uv sync` untuk development meng-install semuanya, karena grup `dev` mereferensikan
`agent-service[service,ui]`. Untuk satu komponen saja: `uv sync --no-dev --extra service`.

URL UI berisi `user_id`, `thread_id`, dan `agent`. Simpan atau bagikan URL itu untuk membuka ulang
percakapan. Siapa pun yang memegang URL tersebut bisa membaca thread-nya.

### Docker Compose

```bash
docker compose up --build        # Postgres, migrasi, API di :8080, UI di :8501
docker compose down              # hentikan (tambahkan -v untuk menghapus data Postgres)
```

- **Model:** stack memakai FakeModel secara default, jadi bisa jalan tanpa API key. Konfigurasi LLM
  di `.env` sengaja tidak dipakai di dalam container.
- **Variabel yang diambil dari shell atau `.env`:** `AUTH_SECRET` (dipakai service dan UI) dan
  `LOG_LEVEL`. Port bisa dipindah dengan `SERVICE_PORT` dan `UI_PORT`.
- **Urutan start:** `postgres` (healthy) → `migrate` (Alembic + tabel checkpointer, lalu selesai)
  → `agent-service` → `ui`. Migrasi tidak dijalankan di lifespan, supaya beberapa replika tidak
  menjalankannya bersamaan.
- **Data:** thread tersimpan di volume `postgres-data`. Postgres hanya dibuka di `127.0.0.1`
  (port `POSTGRES_PORT`, default 5432). Kredensial dev bisa diganti lewat `POSTGRES_USER`,
  `POSTGRES_PASSWORD`, dan `POSTGRES_DB`.
- **Image:** setiap image hanya membawa extra-nya. Image `service` sekitar 505 MB (tanpa
  Streamlit), dan image `ui` sekitar 881 MB (tanpa LangGraph). Sebelumnya keduanya sekitar 1 GB.

Untuk LLM OpenAI-compatible asli (nilai `LLM_*` dan `DEFAULT_MODEL` dibaca dari `.env`):

```bash
docker compose -f compose.yaml -f compose.llm.yaml up --build
```

Jika LLM berjalan di host (misalnya Ollama di `localhost:11434`), set
`DOCKER_LLM_BASE_URL=http://host.docker.internal:11434/v1`. Dari dalam container, `localhost`
menunjuk ke container itu sendiri.

## Konfigurasi

| Variabel | Wajib | Keterangan |
|---|---|---|
| `LLM_BASE_URL` | ya* | Endpoint OpenAI-compatible |
| `LLM_API_KEY` | ya* | API key |
| `DEFAULT_MODEL` | ya* | Model default |
| `AVAILABLE_MODELS` | tidak | Allowlist model, dipisah koma |
| `USE_FAKE_MODEL` | tidak | `true` untuk dev/test tanpa LLM |
| `LLM_MAX_TOKENS` | tidak | Batas token jawaban per giliran model, default `8192`. Pada model reasoning (Ollama), token reasoning ikut dihitung. Jawaban yang terpotong ditandai `truncated` |
| `LLM_MAX_TOKENS_PARAM` | tidak | Nama parameter batas token di request: `max_tokens` (default, untuk Ollama/vLLM/llama.cpp) atau `max_completion_tokens` (model reasoning OpenAI seperti gpt-5/o-series) |
| `DATABASE_URL` | tidak | Postgres, default `postgresql://agent:agent@127.0.0.1:5432/agent_service` (service `postgres` di compose). Pakai `127.0.0.1`, bukan `localhost`, di Docker Desktop Windows |
| `AUTH_SECRET` | tidak | Jika diset, semua request butuh `Authorization: Bearer ...` |
| `FIRECRAWL_API_KEY` | tidak | Key [Firecrawl](https://firecrawl.dev) untuk tool `web_search` (research-assistant, supervisor). Kosong = tanpa pencarian web |
| `AGENT_URL` | tidak | URL service untuk UI/client, default `http://localhost:8080` |

\* Tidak wajib jika `USE_FAKE_MODEL=true`. Daftar lengkap ada di [PRD.md §8](PRD.md#8-konfigurasi-env-var-v1).

## API Singkat

| Method | Path | Fungsi |
|---|---|---|
| GET | `/info` | Daftar agent dan model |
| POST | `/{agent_id}/invoke` | Jalankan agent, kembalikan jawaban akhir |
| POST | `/{agent_id}/stream` | Jalankan agent dengan streaming SSE |
| POST | `/{agent_id}/history` | Riwayat satu thread |
| GET | `/{agent_id}/threads` | Daftar thread milik user |
| PATCH | `/{agent_id}/threads/{thread_id}` | Ganti judul thread |
| DELETE | `/{agent_id}/threads/{thread_id}` | Hapus thread beserta riwayatnya |
| GET | `/health` | Health check, selalu tanpa auth |

Response `/invoke` dan `/stream` membawa header `X-Thread-Id` dan `X-User-Id`. Kirim keduanya lagi
untuk melanjutkan thread yang sama. Thread milik user lain menjawab 404.

```bash
curl -N -X POST http://localhost:8080/chatbot/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Halo!", "stream_tokens": true}'
```

## Menggunakan AgentClient

```python
from agent_service.client import AgentClient

with AgentClient(base_url="http://localhost:8080", agent_id="chatbot", auth_secret=None) as client:
    reply = client.invoke("Halo!", user_id="user-1")
    print(reply.message.content, reply.thread_id)

    # Lanjutkan thread yang sama. Event: TokenEvent, MessageEvent, atau ErrorEvent.
    with client.stream("Lanjut", thread_id=reply.thread_id, user_id="user-1") as run:
        for event in run:
            print(event)

    print(client.get_threads("user-1").threads)
```

Setiap method punya versi async berawalan `a` (`ainvoke`, `astream` dengan `async with`, dan
seterusnya). Error HTTP atau koneksi dilempar sebagai `AgentClientError` dengan `status_code`
dan `detail`.

## Menambah Agent Baru

Langkah lengkap dengan contoh kode ada di
[docs/ARCHITECTURE.md § Menambah Agent](docs/ARCHITECTURE.md#menambah-agent). Ringkasnya:
buat subclass `BaseAgent` yang mengimplementasikan `build(model, checkpointer)`, daftarkan di
`create_default_agents()` (`agents/catalog.py`), lalu tulis test dengan `FakeModel`. Service
dan UI otomatis menampilkan agent baru.

## Development

```bash
docker compose up -d postgres # database untuk test (sekali per sesi kerja)
uv run pytest                 # test (tanpa test integration)
uv run pytest -m integration  # test e2e Docker Compose (butuh Docker)
uv run alembic revision --autogenerate -m "add projects"   # migrasi baru dari memory/tables.py
uv run ruff check . --fix     # lint
uv run ruff format .          # format
uv run pyrefly check          # type check
pre-commit install            # pasang git hook
```

Test database membuat database sementara `agent_service_test_<acak>` di server Postgres, menjalankan
migrasi sekali per sesi, mengosongkan tabel sebelum setiap test, lalu menghapus database itu.
Server lain bisa dipakai lewat `TEST_DATABASE_URL`.

Aturan penulisan kode (prosedur 5 langkah, Class vs Function, checklist Zen) ada di
[AGENTS.md](AGENTS.md). Wajib dibaca sebelum berkontribusi.

## Dokumentasi

| Dokumen | Isi |
|---|---|
| [AGENTS.md](AGENTS.md) | Aturan kode dan workflow untuk coding agent dan kontributor |
| [PRD.md](PRD.md) | Requirement, kontrak API, scope, milestone |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Lifespan, alur request, kepemilikan thread, cara menambah agent |
| [.agents/memory.md](.agents/memory.md) | Status, decision log, pelajaran dari kode lama |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Daftar fitur, urutan eksekusi, rencana commit per fitur |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Git lifecycle: branch, commit message, PR, release, hotfix |
| [`agent-service-toolkit/`](agent-service-toolkit/) | Kode asli (referensi, read-only) |
