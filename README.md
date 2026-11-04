# LangGraph Agent Service

Service untuk menjalankan beberapa agent [LangGraph](https://langchain-ai.github.io/langgraph/)
lewat satu API FastAPI, lengkap dengan streaming SSE, Python client, dan UI chat Streamlit.

Project ini adalah rewrite dari [`agent-service-toolkit/`](agent-service-toolkit/) dengan fokus pada
kode yang sederhana, eksplisit, dan mudah dites (Zen of Python).

> **Status:** v0.1.0 (service) sudah dirilis. M2 berjalan: `AgentClient` sudah tersedia, UI Streamlit belum. Lihat [PRD.md](PRD.md) untuk requirement dan
> [.agents/memory.md](.agents/memory.md) untuk status terkini.

## Fitur

- **Multi-agent registry**: pilih agent lewat URL `/{agent_id}/...`.
- **Streaming SSE**: token dan message (termasuk tool call dan sub-agent) dikirim secara real-time.
- **Percakapan persisten**: riwayat thread disimpan di SQLite via LangGraph checkpointer.
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
│ (client/)    │            │              ModelFactory  SQLite        │
└──────────────┘            │              (llm/)        checkpointer  │
                            └──────────────────────────────────────────┘
```

## Quickstart

Prasyarat: Python 3.12+ dan [uv](https://docs.astral.sh/uv/).

```bash
# 1. Install dependency
uv sync

# 2. Konfigurasi
cp .env.example .env
# isi LLM_BASE_URL, LLM_API_KEY, DEFAULT_MODEL
# atau USE_FAKE_MODEL=true untuk mencoba tanpa API key

# 3. Jalankan service (http://localhost:8080, docs di /docs)
uv run python -m agent_service.run_service

# 4. Jalankan UI di terminal lain (http://localhost:8501)
uv run streamlit run src/agent_service/ui/app.py
```

### Docker Compose

```bash
docker compose up --build
```

## Konfigurasi

| Variabel | Wajib | Keterangan |
|---|---|---|
| `LLM_BASE_URL` | ya* | Endpoint OpenAI-compatible |
| `LLM_API_KEY` | ya* | API key |
| `DEFAULT_MODEL` | ya* | Model default |
| `AVAILABLE_MODELS` | tidak | Allowlist model, dipisah koma |
| `USE_FAKE_MODEL` | tidak | `true` untuk dev/test tanpa LLM |
| `SQLITE_DB_PATH` | tidak | Default `checkpoints.db` |
| `AUTH_SECRET` | tidak | Jika diset, semua request butuh `Authorization: Bearer ...` |
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
uv run pytest                 # test
uv run ruff check . --fix     # lint
uv run ruff format .          # format
uv run pyrefly check          # type check
pre-commit install            # pasang git hook
```

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
