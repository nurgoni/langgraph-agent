# Changelog

Semua perubahan penting dicatat di file ini. Format mengikuti
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), dan versi mengikuti
[Semantic Versioning](https://semver.org/). Proses rilis ada di [CONTRIBUTING.md](CONTRIBUTING.md#release).

## [Unreleased]

### Added

- Project sebagai agent deklaratif (FR-36, ADR 0004): CRUD `/projects`, chat di
  `/projects/{project_id}/invoke|stream|history|threads`, dan project built-in read-only
  (`general-assistant`, `research-assistant`) yang di-seed saat startup. Project memilih agent
  dasar (tidak bisa diganti), model (request → project → default), instruksi, skill, dan
  `settings.max_tokens` (FR-30). Menghapus project ikut menghapus thread-nya.
  `ThreadSummary.project_id`, dan `AgentClient` mendapat `project_id` serta method CRUD project
  (F26).
- System prompt dirakit setiap giliran oleh `ContextBuilder` (FR-37): instruksi agent, instruksi
  project, slot skill (F28) dan memory (F30), lalu bagian lingkungan (tanggal dan timezone), masing-
  masing dengan batas ukuran. Instruksi project kini benar-benar sampai ke model (F27).

- Skill built-in (FR-38, ADR 0005): `meeting-notes` dan `research-report` dalam format Agent Skills,
  divalidasi saat startup (yang tidak valid dilewati dan dicatat di log). `GET /skills` dan
  `GET /skills/{scope}/{name}`. Model melihat daftar skill aktif project di system prompt dan
  memuat isinya lewat tool `load_skill(name, path?)`, yang hanya muncul jika project punya skill
  aktif. Project built-in kini membawa skill. `AgentClient.list_skills()`/`get_skill()` (F28).
- Context management (FR-39): riwayat yang dikirim ke model dijaga di bawah `CONTEXT_MAX_TOKENS`
  (default 16.000). Saat terlampaui, giliran lama diringkas oleh model (tanpa di-stream) sampai
  riwayat langsung tinggal ±50%. Ringkasan disimpan di state thread dan masuk ke system prompt.
  Tool call dan hasilnya tidak pernah dipisah, dan `/history` tetap lengkap (F29).
- Long-term memory per user (FR-40) untuk `chatbot` dan `research-assistant`: tool `save_memory`
  meminta persetujuan lewat interrupt (balas "yes"/"ya" untuk menyimpan), `search_memory` mencari
  dengan kata kunci, dan 20 memory terbaru masuk ke system prompt di semua thread user.
  `GET /memories`, `DELETE /memories/{memory_id}`, dan `AgentClient.list_memories()`/
  `delete_memory()`. Memory disimpan di `AsyncPostgresStore`; **jalankan ulang `run_migrate`**
  (revisi 0004) sebelum start (F30).

### Changed

- `BaseAgent.build(model, checkpointer, store=None)` dan `AgentRegistry(..., store=None)`: store
  long-term memory diberikan saat graph dibangun. Agent custom perlu menambah parameter `store`.
  Slot `memory` di konstruktor `ContextBuilder` diganti argumen `memories` per panggilan, karena
  memory dibaca async dari store (F30).

- **Breaking (belum dirilis):** `Project.skill_ids` berisi ID skill `<scope>/<name>`
  (`builtin/research-report`), dan ID yang tidak dikenal ditolak (422). `ChatbotAgent` kini dibangun
  di atas `ToolCallingAgent`, sehingga bisa memakai skill (F28).
- Semua agent, termasuk `chatbot`, mendapat bagian lingkungan di akhir system prompt, sehingga
  model tahu tanggal hari ini. `ToolCallingAgent` menerima `ContextBuilder` alih-alih
  `system_prompt` + `clock`, dan placeholder `{current_date}` tidak dipakai lagi (F27).

### Fixed

- `.env.example` tidak lagi mengisi `LLM_MAX_TOKENS_PARAM=max_completion_tokens`. Ollama
  mengabaikan parameter itu, sehingga batas token tidak berlaku bagi yang menyalin contoh ini.

## [0.4.0] - 2026-11-15

M4 Foundation: Postgres, login per user, batas token jawaban, image lebih kecil, dan kontrak API
yang dipublikasikan.

**Catatan upgrade (breaking):**

1. Jalankan Postgres (`docker compose up -d postgres`), lalu
   `uv run python -m agent_service.run_migrate`. Data `checkpoints.db` lama tidak dimigrasi.
2. Isi `JWT_SECRET` (minimal 32 karakter) dan hapus `AUTH_SECRET` dari `.env`.
3. Buat akun: `uv run python -m agent_service.manage create-user <username>`.
4. Client harus login (`AgentClient.login()` atau `POST /auth/login`) dan tidak lagi mengirim
   `user_id`.

### Added

- Batas token jawaban `LLM_MAX_TOKENS` (default 8192) untuk model OpenAI-compatible, bisa ditimpa
  lewat `ModelFactory.create(..., max_tokens=...)`. Jawaban yang berhenti karena batas
  (`finish_reason = "length"`) ditandai `ChatMessage.truncated` di `/invoke`, `/stream`, dan
  `/history`, dan UI menampilkan peringatan "jawaban terpotong". `LLM_MAX_TOKENS_PARAM` memilih nama
  parameter di request (`max_tokens` untuk Ollama, `max_completion_tokens` untuk model reasoning
  OpenAI) (F21).
- Dependency dipisah menjadi extras: install dasar hanya `schema` + `client` (pydantic, httpx),
  extra `service` untuk API, dan extra `ui` untuk Streamlit. Image Docker hanya meng-install
  extra-nya: image `service` turun dari ±1 GB ke ±505 MB dan tanpa Streamlit, image `ui` ±881 MB
  dan tanpa LangGraph (F22).
- Login per user (FR-33): `POST /auth/login` menukar username dan password (hash argon2id) dengan
  access token JWT HS256 (`JWT_SECRET`, `JWT_TTL_SECONDS`, default 12 jam, tanpa refresh token).
  Akun dibuat lewat `python -m agent_service.manage create-user <username> [--role service]`.
  `AgentClient.login()`/`alogin()`, dan form login + logout di UI Streamlit (F24).
- CORS untuk origin di `CORS_ORIGINS` (FR-34), dengan header `X-Thread-Id` diekspos ke browser
  (F24).
- Kontrak API dipublikasikan di `contracts/openapi.json` dan `contracts/stream-event.schema.json`
  (FR-35), dihasilkan oleh `python -m agent_service.export_contracts`. CI dan hook pre-commit gagal
  jika file tidak sinkron dengan kode. Header `X-Thread-Id` kini tercatat di OpenAPI (F25).
- Rencana Fase 2 (M4–M10, F21–F46): requirement FR-30–FR-58 dan NFR-9–NFR-12 di PRD, rincian
  fitur dan backlog di ROADMAP, serta ADR 0001–0005 (Postgres-only, harness sendiri, frontend
  React, Project sebagai agent deklaratif, format skill) di `docs/adr/`.

### Changed

- **Breaking:** `user_id` diambil dari access token. Field `user_id` dihapus dari semua request
  (`UserInput`, `ChatHistoryInput`, `ThreadRenameInput`, query `/threads` dan `DELETE`), header
  `X-User-Id` dihapus, dan method `AgentClient` tidak lagi menerima `user_id`. URL UI tidak lagi
  berisi `user_id`. Semua endpoint selain `/health` dan `/auth/login` butuh token (F24).
- **Breaking:** persistence pindah ke Postgres (ADR 0001): checkpointer `AsyncPostgresSaver` dan
  tabel `thread_metadata` lewat SQLAlchemy Core async + Alembic, dengan satu env `DATABASE_URL`
  (default Postgres compose lokal). `docker compose up` kini menjalankan `postgres` → `migrate` →
  service. Service menolak start jika database tidak terjangkau atau migrasi belum dijalankan
  (`python -m agent_service.run_migrate`) (F23).

### Removed

- `AUTH_SECRET` (shared bearer token) dan opsi `auth_secret` di `AgentClient`, diganti JWT per user
  (F24).
- SQLite: `SQLITE_DB_PATH`, `aiosqlite`, `langgraph-checkpoint-sqlite`, dan volume compose
  `agent-data`. Data di `checkpoints.db` lama tidak dimigrasi (F23).

## [0.3.0] - 2026-11-12

### Added

- Reasoning model terlihat: field reasoning dari provider OpenAI-compatible (`reasoning`/
  `reasoning_content`) diteruskan sebagai frame SSE `reasoning` sebelum token jawaban, disimpan
  di `ChatMessage.reasoning`, dan ditampilkan di blok "Thinking" UI yang bisa dibuka-tutup
  (F19).
- Agent `research-assistant`: `ToolCallingAgent` generik dengan tool web search dan kalkulator
  numexpr. Error tool dikembalikan ke model agar bisa dicoba ulang (F15).
- Agent `interrupt-agent`: menanyakan tanggal lahir lewat `interrupt()` jika belum diketahui, lalu
  melanjutkan dari jawaban user (resume). Ulangan pertanyaan berjalan lewat edge graph, tanpa
  rekursi atau mutasi state (F16).
- Agent `supervisor`: mendelegasikan tugas ke `math_expert` dan `research_expert`, dengan model
  dari request. Message expert ditandai `ChatMessage.agent`, dikirim bertahap selama expert
  bekerja, dan dirender bertingkat di UI (F17).
- Tool `web_search` berbasis Firecrawl Search API (dipakai `research-assistant` dan
  `research_expert`). Key dibaca dari env baru `FIRECRAWL_API_KEY`. Tanpa key, tool menjawab
  "not configured" dan agent tetap berjalan (F20).

## [0.2.0] - 2026-11-05

### Added

- `AgentClient` sync dan async: `invoke` (mengembalikan `AgentReply` berisi ID thread/user),
  `stream` (context manager `StreamRun`), history, daftar thread, rename, delete, dan info yang
  diambil lazy. Error HTTP dibungkus `AgentClientError` dengan status dan detail (F11).
- UI chat Streamlit: token streaming, tool call sebagai status yang bisa di-expand, pertanyaan
  interrupt sebagai pesan AI, dan error service ditampilkan di chat (F12).
- Sidebar UI: chat baru, pemilih agent dan model, toggle streaming, daftar thread dengan aksi
  rename dan hapus. `user_id`, `thread_id`, dan `agent` disimpan di URL sehingga percakapan bisa
  dibuka ulang (F13).
- Stack Docker Compose (service + UI) dengan FakeModel sebagai default, override `compose.llm.yaml`
  untuk LLM asli, test e2e bermarker `integration`, dan job CI `e2e` (F14).

### Fixed

- Model OpenAI-compatible kini dibuat dengan `streaming=True`, sehingga `/stream` mengirim token
  satu per satu untuk LLM asli, bukan satu chunk berisi seluruh jawaban (F11).
- UI menampilkan URL service dan perintah untuk menjalankannya saat service tidak terjangkau,
  bukan error socket mentah. Client membedakannya lewat `ServiceUnreachableError` (F12).

## [0.1.0] - 2026-11-04

### Added

- Dokumen fondasi: AGENTS.md, PRD.md, README.md, CONTRIBUTING.md, docs/ROADMAP.md,
  .agents/memory.md.
- Tooling project: uv, ruff, pyrefly, pytest, pre-commit, CI GitHub Actions (F00).
- `Settings` berbasis pydantic-settings dengan validasi konfigurasi LLM dan allowlist model,
  konstanta bernama, dan `configure_logging` (F01).
- Schema API: model request, response, dan event SSE. `ChatHistoryInput` mewajibkan `user_id`
  (F04).
- `ModelFactory` untuk model OpenAI-compatible dengan allowlist dan cache per instance, serta
  `FakeModel` dengan respons dan tool call yang bisa di-script. Unit test kini gagal jika membuka
  koneksi network (F02).
- `CheckpointerProvider`: async context manager untuk `AsyncSqliteSaver` yang menyiapkan tabel
  saat dibuka dan menutup koneksi saat keluar (F03).
- `BaseAgent` dengan `config_schema` per agent, `AgentRegistry` yang meng-compile graph per agent dan
  model, error `AgentNotFoundError`/`AgentUnavailableError`, dan agent `chatbot` (F05).
- Service FastAPI: `create_app` dengan lifespan, bearer auth opsional, pemetaan error domain ke
  404/422/503, endpoint `/health` dan `/info`, serta entrypoint `run_service` (F06).
- Endpoint `/invoke` dan `/history` (juga varian agent default). ID thread/user dikembalikan lewat
  header `X-Thread-Id`/`X-User-Id`, thread milik user atau agent lain menjawab 404, dan
  `agent_config` divalidasi per agent (F07).
- Endpoint `/threads`: daftar thread milik user per agent, yang terakhir di-update lebih dulu,
  dengan `limit` 1–100 (F09).
- Rename (`PATCH`) dan hapus (`DELETE`) thread. Judul custom disimpan di tabel `thread_metadata`
  dan tampil di listing. Thread milik user lain menjawab 404 (F18).
- Endpoint `/stream` (SSE): frame `token`, `message`, dan `error`, selalu diakhiri `[DONE]`, dengan
  header ID dan cek kepemilikan yang sama seperti `/invoke` (F08).
- `docs/ARCHITECTURE.md`: lifespan, alur request, kepemilikan thread, error, persistence, dan cara
  menambah agent (F10).

[Unreleased]: https://github.com/nurgoni/langgraph-boilerplate-agent/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/nurgoni/langgraph-boilerplate-agent/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/nurgoni/langgraph-boilerplate-agent/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/nurgoni/langgraph-boilerplate-agent/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/nurgoni/langgraph-boilerplate-agent/releases/tag/v0.1.0
