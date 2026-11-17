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

#    isi JWT_SECRET (wajib, minimal 32 karakter):
#    uv run python -c "import secrets; print(secrets.token_urlsafe(48))"

# 3. Jalankan Postgres, siapkan skemanya, dan buat akun login
docker compose up -d postgres
uv run python -m agent_service.run_migrate
uv run python -m agent_service.manage create-user demo   # password ditanya dua kali

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

UI meminta login dengan akun dari `manage create-user`. URL UI berisi `thread_id` dan `agent`,
tanpa identitas user, jadi URL yang dibagikan hanya bisa dibuka oleh pemilik thread.

### Docker Compose

```bash
docker compose up --build        # Postgres, migrasi, API di :8080, UI di :8501
docker compose down              # hentikan (tambahkan -v untuk menghapus data Postgres)
```

- **Model:** stack memakai FakeModel secara default, jadi bisa jalan tanpa API key. Konfigurasi LLM
  di `.env` sengaja tidak dipakai di dalam container.
- **Variabel yang diambil dari shell atau `.env`:** `JWT_SECRET` (default nilai dev yang tidak
  aman, ganti di luar mesin dev), `JWT_TTL_SECONDS`, `CORS_ORIGINS`, dan `LOG_LEVEL`. Port bisa
  dipindah dengan `SERVICE_PORT` dan `UI_PORT`.
- **Akun:** `docker compose exec agent-service python -m agent_service.manage create-user demo`.
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
| `CONTEXT_MAX_TOKENS` | tidak | Anggaran token riwayat (beserta ringkasannya) yang dikirim ke model setiap panggilan, default `16000`, minimum `1000`. Jika terlampaui, giliran lama diringkas sampai riwayat langsung tinggal ±50%. `/history` tetap lengkap |
| `LLM_MAX_TOKENS_PARAM` | tidak | Nama parameter batas token di request: `max_tokens` (default, untuk Ollama/vLLM/llama.cpp) atau `max_completion_tokens` (model reasoning OpenAI seperti gpt-5/o-series) |
| `DATABASE_URL` | tidak | Postgres, default `postgresql://agent:agent@127.0.0.1:5432/agent_service` (service `postgres` di compose). Pakai `127.0.0.1`, bukan `localhost`, di Docker Desktop Windows |
| `JWT_SECRET` | **ya** | Kunci penanda tangan access token (HS256), minimal 32 karakter. Service menolak start tanpa nilai ini |
| `JWT_TTL_SECONDS` | tidak | Umur access token, default `43200` (12 jam). Tidak ada refresh token |
| `CORS_ORIGINS` | tidak | Origin browser yang boleh memanggil API, dipisah koma. Kosong = tidak ada |
| `FIRECRAWL_API_KEY` | tidak | Key [Firecrawl](https://firecrawl.dev) untuk tool `web_search` (research-assistant, supervisor). Kosong = tanpa pencarian web |
| `AGENT_URL` | tidak | URL service untuk UI/client/eval, default `http://localhost:8080` |
| `EVAL_USERNAME`, `EVAL_PASSWORD` | eval | Akun untuk `run_evals`, sebaiknya service account (`--role service`) |
| `EVAL_TIMEOUT_SECONDS` | tidak | Batas waktu per request eval, default `300` |

\* Tidak wajib jika `USE_FAKE_MODEL=true`. Daftar lengkap ada di [PRD.md §8](PRD.md#8-konfigurasi-env-var-v1).

## API Singkat

| Method | Path | Fungsi |
|---|---|---|
| POST | `/auth/login` | Tukar username dan password dengan access token, tanpa auth |
| GET | `/info` | Daftar agent dan model |
| POST | `/{agent_id}/invoke` | Jalankan agent, kembalikan jawaban akhir |
| POST | `/{agent_id}/stream` | Jalankan agent dengan streaming SSE |
| POST | `/{agent_id}/history` | Riwayat satu thread |
| GET | `/{agent_id}/threads` | Daftar thread milik user |
| PATCH | `/{agent_id}/threads/{thread_id}` | Ganti judul thread |
| DELETE | `/{agent_id}/threads/{thread_id}` | Hapus thread beserta riwayatnya |
| GET, POST | `/projects` | Daftar project (built-in + milik user), buat project |
| GET, PATCH, DELETE | `/projects/{project_id}` | Satu project. Built-in read-only (403). Hapus = ikut hapus thread-nya |
| POST | `/projects/{project_id}/invoke`, `/stream`, `/history` | Chat di dalam project |
| GET, PATCH, DELETE | `/projects/{project_id}/threads[/{thread_id}]` | Thread di dalam project |
| GET | `/skills`, `/skills/{scope}/{name}` | Skill yang bisa diaktifkan di project (read-only) |
| GET | `/memories` | Long-term memory milik user, yang terakhir diubah lebih dulu |
| DELETE | `/memories/{memory_id}` | Hapus satu memory. Memory user lain menjawab 404 |
| GET | `/runs/{run_id}/trace` | Trace satu run: durasi, token, panggilan model dan tool. Run user lain menjawab 404 |
| GET | `/health` | Health check, selalu tanpa auth |

Semua endpoint selain `/health` dan `/auth/login` butuh `Authorization: Bearer <access_token>`.
Identitas user diambil dari token, bukan dari body atau query. Response `/invoke` dan `/stream`
membawa header `X-Thread-Id`; kirim lagi sebagai `thread_id` untuk melanjutkan thread yang sama.
Thread milik user lain menjawab 404.

```bash
TOKEN=$(curl -s -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "password": "..."}' | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
curl -N -X POST http://localhost:8080/chatbot/stream \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message": "Halo!", "stream_tokens": true}'
```

Kontrak lengkap ada di [`contracts/openapi.json`](contracts/openapi.json) dan
[`contracts/stream-event.schema.json`](contracts/stream-event.schema.json) (satu frame SSE). Keduanya
dihasilkan dari kode dan dicek CI, jadi aman dipakai untuk generate client bertipe.

### Project

Project adalah agent deklaratif ([ADR 0004](docs/adr/0004-project-as-declarative-agent.md)): satu
agent kode (`base_agent_id`, tidak bisa diganti), ditambah model, instruksi, skill, dan
`settings.max_tokens`. Chat di project memakai route `/projects/{project_id}/...`. Model yang
dipakai: model di request, lalu model project, lalu `DEFAULT_MODEL`. Thread project hanya bisa
dibuka lewat project-nya. Project built-in (`general-assistant`, `research-assistant`) di-seed saat
startup dan read-only.

```python
from agent_service.schema.projects import ProjectCreate

project = client.create_project(
    ProjectCreate(
        name="Riset pasar",
        base_agent_id="research-assistant",
        instructions="Jawab dalam Bahasa Indonesia.",
        settings={"max_tokens": 2048},
    )
)
client.project_id = project.id  # chat dan thread berikutnya masuk ke project ini
reply = client.invoke("Siapa pemain utama pasar EV di Asia Tenggara?")
```

### Skill

Skill adalah instruksi prosedural (format [Agent Skills](https://agentskills.io)) yang dimuat model
hanya saat relevan ([ADR 0005](docs/adr/0005-skill-format-and-sources.md)). Skill built-in ada di
`src/agent_service/skills/builtin/<name>/SKILL.md`: `meeting-notes` dan `research-report`.

- Aktifkan skill di project lewat `skill_ids`, dengan ID dari `GET /skills`
  (`builtin/research-report`).
- Setiap giliran, system prompt berisi daftar nama + deskripsi skill aktif, dan model memanggil
  tool `load_skill(name, path?)` untuk isi lengkapnya. Tool ini hanya muncul jika project punya skill
  aktif, dan hanya bisa memuat skill yang aktif di project itu.
- Skill dengan `SKILL.md` tidak valid dilewati saat startup dan dicatat di log.

### Long-term memory

`chatbot` dan `research-assistant` bisa mengingat fakta tentang user lintas thread.

- Saat user meminta sesuatu diingat, model memanggil `save_memory`, dan agent bertanya dulu:
  `Save this to memory for future conversations? "..." Reply "yes" to save it`. Balas `yes`, `ya`,
  `ok`, atau `simpan` untuk menyimpan. Balasan lain membatalkan, dan model menanggapi balasan itu.
- Hingga 20 memory terbaru masuk ke system prompt setiap giliran. Model mencari memory lama lewat
  tool `search_memory` (pencarian kata, belum memakai embedding).
- Memory tersimpan per user (maksimal 200), dilihat lewat `GET /memories`, dan dihapus lewat
  `DELETE /memories/{memory_id}` (`AgentClient.list_memories()`/`delete_memory()`).
- Setelah update ke versi ini, jalankan lagi `run_migrate` untuk membuat tabel store. Tanpa itu,
  service menolak start.

### Trace dan eval

Setiap run `/invoke` dan `/stream` menyimpan trace di tabel `run_traces`: durasi run, setiap
panggilan model (dengan token, jika provider mengirim usage) dan tool, serta status (`ok`, `error`,
`interrupted`). Isi prompt dan hasil tool tidak disimpan. `run_id` ada di setiap `ChatMessage`,
dan trace dibaca lewat `GET /runs/{run_id}/trace` atau `AgentClient.get_run_trace(run_id)`.

Eval menjalankan dataset YAML di `evals/` lewat `AgentClient`, dengan jalur yang sama seperti user,
lalu menulis laporan JSON + Markdown ke `eval-reports/` (tidak di-commit):

```bash
uv run python -m agent_service.manage create-user evals --role service
# isi EVAL_USERNAME=evals dan EVAL_PASSWORD di .env, lalu dengan service berjalan:
uv run python -m agent_service.run_evals evals/skills.yaml
```

Cek per kasus: `contains`, `not_contains`, `tools_called`, `tools_not_called`, `skills_loaded`, dan
`max_latency_seconds`. Exit code 1 jika ada kasus gagal. `evals/smoke.yaml` (FakeModel) ikut
dijalankan pytest di CI.

## Menggunakan AgentClient

```python
from agent_service.client import AgentClient

with AgentClient(base_url="http://localhost:8080", agent_id="chatbot") as client:
    client.login("demo", "rahasia-demo")  # token dipakai untuk request berikutnya
    reply = client.invoke("Halo!")
    print(reply.message.content, reply.thread_id)

    # Lanjutkan thread yang sama. Event: TokenEvent, MessageEvent, atau ErrorEvent.
    with client.stream("Lanjut", thread_id=reply.thread_id) as run:
        for event in run:
            print(event)

    print(client.get_threads().threads)
```

Setiap method punya versi async berawalan `a` (`ainvoke`, `astream` dengan `async with`, dan
seterusnya). Error HTTP atau koneksi dilempar sebagai `AgentClientError` dengan `status_code`
dan `detail`. Token yang kedaluwarsa menghasilkan 401; panggil `login()` lagi. Token yang sudah
ada (misalnya disimpan aplikasi) bisa dipakai lewat `AgentClient(access_token=...)` atau
`set_access_token()`.

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
uv run python -m agent_service.export_contracts            # ekspor ulang contracts/ setelah ubah API
uv run python -m agent_service.run_evals evals/skills.yaml # eval dengan model asli (service berjalan)
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
