# ROADMAP

Breakdown [PRD.md](../PRD.md) menjadi fitur-fitur yang bisa dikembangkan satu per satu, beserta
urutan eksekusinya. Aturan git (branch, commit, PR, release) ada di
[CONTRIBUTING.md](../CONTRIBUTING.md). Aturan kode ada di [AGENTS.md](../AGENTS.md).

**Aturan dasar:** 1 fitur = 1 branch `feature/Fxx-<slug>` = 1 PR ke `develop` = 1 squash commit.

Referensi kode lama ditulis relatif terhadap `agent-service-toolkit/src/`.

## Status

Status: `todo` → `in-progress` → `done`. Perbarui kolom ini di PR yang menyelesaikan fitur.

| ID | Fitur | Milestone | Status |
|---|---|---|---|
| F00 | Project bootstrap | M0 | done |
| F01 | Core settings | M1 | done |
| F02 | LLM model factory | M1 | done |
| F03 | SQLite checkpointer | M1 | done |
| F04 | API schema | M1 | done |
| F05 | Agent registry | M1 | done |
| F06 | Service app | M1 | done |
| F07 | Invoke & history | M1 | done |
| F08 | SSE streaming | M1 | done |
| F09 | User threads | M1 | done |
| F18 | Thread rename & delete | M1 | done |
| F10 | Architecture docs | M1 | done |
| F11 | Agent client | M2 | done |
| F12 | UI chat | M2 | done |
| F13 | UI sidebar & threads | M2 | done |
| F14 | Docker Compose & e2e | M2 | done |
| F19 | Reasoning display | M3 | done |
| F15 | Research assistant | M3 | done |
| F16 | Interrupt agent | M3 | todo |
| F17 | Supervisor agent | M3 | todo |

## Milestone & Rilis

| Milestone | Fitur | Rilis | Hasil |
|---|---|---|---|
| M0: Bootstrap | F00 | – | Repo, tooling, dan CI siap |
| M1: Core + Service | F01–F10, F18 | `v0.1.0` | API lengkap dengan `chatbot`, dites dengan FakeModel |
| M2: Client + UI | F11–F14 | `v0.2.0` | Chat end-to-end via Docker Compose |
| M3: Agent tambahan | F19, F15–F17 | `v0.3.0` | Reasoning terlihat, tool calling, human-in-the-loop, multi-agent |

## Dependency Graph

```text
F00 ─► F01 ─┬─► F02 ─┐
            └─► F03 ─┴─► F05 ─► F06 ─┬─► F07 ─┬─► F08 ─► F10
F00 ─► F04 ──────────────────────────┘        └─► F16
                                    F06 ─► F09 ─► F18
F04 ─► F11 ─► F12 ─► F13 ─► F14          (F13 juga butuh F18)
F05 ─► F15 ─► F17                        (F17 juga butuh F08, F12)
F08 ─► F19 ◄─ F12                        (F19 juga butuh F02, F11)
```

**Urutan eksekusi yang disarankan (satu developer):**
F00 → F01 → F04 → F02 → F03 → F05 → F06 → F07 → F09 → F18 → F08 → F10 → *rilis v0.1.0* → F11 → F12 →
F13 → F14 → *rilis v0.2.0* → F19 → F15 → F16 → F17 → *rilis v0.3.0*

**Bisa dikerjakan paralel (lebih dari satu developer):**
- F02 ∥ F03 ∥ F04
- F07 ∥ (F09 → F18)
- F11 bisa dimulai setelah F04, karena hanya bergantung pada kontrak dan bisa dites dengan
  `httpx.MockTransport`.
- F15 ∥ M2

## Pemetaan FR → Fitur

| FR | Fitur | | FR | Fitur |
|---|---|---|---|---|
| FR-1 | F05 | | FR-13 | F07 |
| FR-2 | F05 | | FR-14 | F02, F07 |
| FR-3 | F05, F06 | | FR-15 | F05, F06 |
| FR-4 | F05, F17 | | FR-16 | F03 |
| FR-5 | F06 | | FR-17 | F11 |
| FR-6 | F07 | | FR-18 | F11 |
| FR-7 | F08 | | FR-19 | F11 |
| FR-8 | F07 | | FR-20 | F12 |
| FR-9 | F09 | | FR-21 | F13 |
| FR-10 | F06 | | FR-22 | F13 |
| FR-11 | F06 | | FR-23 | F17 |
| FR-12 | F07, F16 | | FR-24 | F12, F16 |
| FR-25 | F18, F13 | | FR-27 | F04, F05, F06, F07 |
| FR-26 | F18, F13 | | FR-28 | F07, F08, F18 |
| FR-29 | F19 | | | |

## Loop Eksekusi per Fitur

1. Siapkan branch:

   ```bash
   git switch develop && git pull
   git switch -c feature/Fxx-<slug>
   ```

2. Baca bagian Fxx di dokumen ini dan [`.agents/memory.md`](../.agents/memory.md). Klarifikasi
   tipe input/output sesuai Langkah 1 di AGENTS.md.
3. Ubah status Fxx menjadi `in-progress`.
4. Kerjakan sesuai **Rencana commit**. Setiap commit lolos pre-commit dan test.
5. Sebelum push, jalankan:

   ```bash
   uv run ruff check . && uv run ruff format --check . && uv run pyrefly check && uv run pytest
   ```

6. Perbarui README, PRD, dan memory.md jika ada perubahan. Ubah status Fxx menjadi `done`.
7. Push, buka PR ke `develop` dengan **Squash title**, tunggu CI hijau dan review, lalu squash
   merge dan hapus branch.
8. Jika Fxx adalah fitur terakhir milestone, jalankan proses rilis (CONTRIBUTING.md § Release).

---

## M0: Bootstrap

### F00: Project bootstrap

- **Branch:** `feature/F00-project-bootstrap`
- **Tujuan:** repo, tooling, dan CI siap, sehingga setiap fitur berikutnya otomatis dicek.
- **Langkah awal (sekali saja, sebelum branch fitur):**

  ```bash
  git init -b main
  # tulis .gitignore minimal (agent-service-toolkit/, .env, *.db) lalu:
  git add AGENTS.md PRD.md README.md CLAUDE.md CONTRIBUTING.md .agents/ docs/ .gitignore
  git commit -m "docs: add project foundation documents"
  git switch -c develop
  ```

- **File:**
  - `.gitignore` (lengkap), `.env.example`, `CHANGELOG.md` (format Keep a Changelog, bagian
    `[Unreleased]`)
  - `pyproject.toml` (`name = "agent-service"`, `version = "0.0.0"`, Python `>=3.12`, ruff, pyrefly,
    dan pytest dengan `--doctest-modules`, marker `integration`), `uv.lock`
  - `.pre-commit-config.yaml` (ruff, ruff-format, pyrefly, end-of-file, trailing-whitespace,
    check-yaml)
  - `src/agent_service/__init__.py` + sub-package kosong (`core`, `llm`, `agents`, `memory`,
    `schema`, `service`, `client`, `ui`)
  - `tests/conftest.py`, `tests/test_smoke.py` (import package)
  - `.github/workflows/ci.yml` (lint, type, test di PR ke `develop`/`main`)
  - `.github/pull_request_template.md`
- **Referensi lama:** `pyproject.toml`, `.pre-commit-config.yaml`, `.github/workflows/test.yml` di
  root toolkit. Ambil versi dependency dan `exclude-newer`.
- **Rencana commit:**
  1. `build: add pyproject with uv, ruff, pyrefly and pytest config`
  2. `build: add src/agent_service package skeleton and smoke test`
  3. `chore: add pre-commit hooks and env example`
  4. `ci: add lint, type check and test workflow`
  5. `docs: add changelog and pull request template`
- **Acceptance criteria:**
  - [ ] `uv sync` dan `uv run pytest` hijau di repo bersih.
  - [ ] `pre-commit run --all-files` hijau.
  - [ ] CI berjalan di PR ke `develop`.
  - [ ] `agent-service-toolkit/` tidak ikut ter-track git.
- **Squash title:** `build: bootstrap project tooling and ci (F00)`

---

## M1: Core + Service → v0.1.0

### F01: Core settings

- **Branch:** `feature/F01-core-settings`
- **FR/NFR:** NFR-1, NFR-7, PRD §8
- **File:** `core/settings.py` (`Settings`), `core/constants.py`, `core/logging_config.py`
  (`configure_logging`), `tests/core/`
- **Penyesuaian saat implementasi:**
  - `LoggingConfigurator` ditulis sebagai function `configure_logging`, karena cuma satu aksi tanpa
    state (aturan praktis di AGENTS.md).
  - File diberi nama `logging_config.py` supaya tidak tertukar dengan modul stdlib `logging`.
- **Catatan desain:**
  - Tidak ada instance `settings` di level modul. Gunakan `Settings()` di lifespan atau
    `Settings.from_env()`.
  - `AVAILABLE_MODELS` di-parse dari string dipisah koma. Default-nya `[DEFAULT_MODEL]`.
  - Validasi: jika `USE_FAKE_MODEL=false`, maka `LLM_BASE_URL`, `LLM_API_KEY`, dan `DEFAULT_MODEL`
    wajib diisi.
- **Referensi lama:** `core/settings.py` (lihat sisi negatifnya di `:178-251` dan `:262`).
- **Rencana commit:**
  1. `feat(core): add named constants for service defaults`
  2. `feat(core): add Settings with env validation and model allowlist`
  3. `feat(core): add configure_logging with standard format`
  4. `docs: record F01 conventions in roadmap, changelog and memory`
- **Acceptance criteria:**
  - [ ] `import agent_service.core.settings` tanpa env tidak raise.
  - [ ] Env yang tidak valid menghasilkan `ValidationError` dengan pesan yang jelas.
- **Squash title:** `feat(core): add settings, constants and logging (F01)`

### F02: LLM model factory

- **Branch:** `feature/F02-llm-model-factory`
- **FR:** FR-4, FR-14
- **File:** `llm/factory.py` (`ModelFactory`, `UnknownModelError`), `llm/fake.py` (`FakeModel`),
  `tests/llm/`
- **Catatan desain:**
  - `ModelFactory(settings).create(model_name) -> BaseChatModel`, dengan cache per nama di dalam
    instance (bukan `@cache` global).
  - Konstanta: `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `DEFAULT_TEMPERATURE`.
  - `FakeModel` mendukung `bind_tools` dan respons tool call yang sudah ditentukan untuk test agent.
- **Referensi lama:** `core/llm.py` (`FakeToolModel` di `:45`, `get_model` di `:67`).
- **Rencana commit:**
  1. `test: block outbound network access in unit tests`
  2. `feat(llm): add FakeModel with scripted tool calls`
  3. `feat(llm): add ModelFactory for openai-compatible models`
  4. `docs: record F02 model factory decisions`
- **Penyesuaian saat implementasi:**
  - Urutan commit dibalik (`FakeModel` dulu, karena dipakai factory). Test ikut di commit kodenya,
    jadi tidak ada commit `test(llm)` terpisah.
  - Ditambah fixture autouse `block_network` di `tests/conftest.py`: koneksi selain loopback gagal,
    kecuali test bertanda `integration`.
  - `FakeModel` ditulis di atas `BaseChatModel`, bukan `GenericFakeChatModel`, karena yang terakhir
    membuang `tool_calls` saat streaming.
  - Ditambah `ModelNotConfiguredError` untuk model non-fake tanpa `LLM_BASE_URL`/`LLM_API_KEY`
    (mungkin terjadi jika `USE_FAKE_MODEL=true` dan allowlist berisi model asli).
  - `create(None)` berarti `DEFAULT_MODEL`.
- **Acceptance criteria:**
  - [x] Model di luar allowlist menghasilkan `UnknownModelError`.
  - [x] Tidak ada network call di test (ditegakkan oleh `block_network`).
- **Squash title:** `feat(llm): add model factory and fake model (F02)`

### F03: SQLite checkpointer

- **Branch:** `feature/F03-sqlite-checkpointer`
- **FR:** FR-16
- **File:** `memory/checkpointer.py` (`CheckpointerProvider`), `tests/memory/`
- **Catatan desain:** async context manager. `async with CheckpointerProvider(settings) as saver:`
  membuka `AsyncSqliteSaver`, menjalankan `setup()` sekali, lalu menutupnya. `__aenter__` tidak
  dipanggil manual.
- **Referensi lama:** `memory/sqlite.py`, `memory/__init__.py`.
- **Rencana commit:**
  1. `feat(memory): add async sqlite CheckpointerProvider`
  2. `docs: record F03 checkpointer decisions`
- **Penyesuaian saat implementasi:**
  - Konstruktor menerima `db_path: Path`, bukan `Settings`. Provider hanya butuh path, dan lifespan
    memanggil `CheckpointerProvider(settings.sqlite_db_path)`.
  - Test ikut di commit kodenya, jadi tidak ada commit `test(memory)` terpisah.
  - Folder induk database dibuat otomatis. Membuka provider yang masih terbuka menghasilkan
    `CheckpointerAlreadyOpenError`, sedangkan provider yang sudah ditutup boleh dibuka lagi.
  - Store (long-term memory) tidak di-port, karena masuk lingkup Future (PRD §9).
- **Acceptance criteria:**
  - [x] Checkpoint yang ditulis bisa dibaca ulang setelah provider dibuka kembali (`tmp_path`).
- **Squash title:** `feat(memory): add sqlite checkpointer provider (F03)`

### F04: API schema

- **Branch:** `feature/F04-api-schema`
- **FR:** kontrak PRD §7, FR-27 (`AgentInfo.config_schema`)
- **File:** `schema/requests.py` (`UserInput`, `StreamInput`, `ChatHistoryInput`,
  `UserThreadsQuery`, `ThreadRenameInput`), `schema/responses.py` (`ChatMessage`, `ToolCall`, `ChatHistory`,
  `ThreadSummary`, `UserThreads`, `AgentInfo`, `ServiceMetadata`), `schema/stream.py`
  (`StreamEvent`), `tests/schema/`
- **Catatan desain:** hanya bergantung pada `pydantic`. **Tidak boleh** import langchain/streamlit.
  Konverter LangChain → `ChatMessage` dikerjakan di F07 (`service/`).
- **Referensi lama:** `schema/schema.py`. Jangan ikut port `schema/task_data.py`, karena di sana UI
  bocor ke schema.
- **Rencana commit:**
  1. `feat(schema): add request models with reserved agent_config keys`
  2. `feat(schema): add response and chat message models`
  3. `feat(schema): add sse stream event model`
  4. `docs: record F04 contract decisions`
- **Penyesuaian saat implementasi:**
  - `ChatHistoryInput` wajib berisi `user_id` (keputusan user, FR-8).
  - `StreamEvent` adalah discriminated union dari `TokenEvent | MessageEvent | ErrorEvent`, ditambah
    `STREAM_EVENT_ADAPTER` dan `STREAM_DONE_MARKER`.
  - `ToolCall` berupa `BaseModel`, bukan TypedDict.
  - Field bebas memakai `JsonValue`, bukan `Any`.
  - Model `Feedback` tidak di-port (LangSmith di luar scope).
- **Acceptance criteria:**
  - [x] `agent_config` yang berisi `thread_id`/`user_id`/`model` ditolak.
  - [x] Test import memastikan tidak ada dependency di luar pydantic (`tests/schema/test_layering.py`).
- **Squash title:** `feat(schema): add api request, response and stream models (F04)`

### F05: Agent registry

- **Branch:** `feature/F05-agent-registry`
- **FR:** FR-1, FR-2, FR-3, FR-4, FR-15, FR-27
- **File:** `agents/base.py` (`BaseAgent`, `EmptyAgentConfig`), `agents/registry.py`
  (`AgentRegistry`), `agents/errors.py` (`AgentNotFoundError`, `AgentUnavailableError`),
  `agents/chatbot.py` (`ChatbotAgent`), `tests/agents/`
- **Catatan desain:**
  - `BaseAgent`: atribut `agent_id`, `description`, `config_schema: type[BaseModel]` (default
    `EmptyAgentConfig` dengan `extra="forbid"`), method
    `build(model, checkpointer) -> CompiledStateGraph`, `async load() -> None` (default no-op), dan
    `parse_config(raw: dict) -> BaseModel`.
  - `AgentRegistry`: `register`, `async load_all()` (agent yang gagal ditandai unavailable dan
    dicatat di log), `get_graph(agent_id, model_name)` (cache graph per pasangan agent + model),
    `list_info()`.
  - Graph di-compile dengan checkpointer. Tidak ada mutasi `graph.checkpointer` setelah compile.
- **Referensi lama:** `agents/agents.py`, `agents/lazy_agent.py`, `agents/chatbot.py`.
- **Rencana commit:**
  1. `feat(agents): add BaseAgent contract with build and load hooks`
  2. `feat(llm): expose model name resolution on ModelFactory`
  3. `feat(agents): add ChatbotAgent as minimal reference agent`
  4. `feat(agents): add AgentRegistry with not-found and unavailable errors`
  5. `docs: record F05 agent registry decisions`
- **Penyesuaian saat implementasi:**
  - Commit config schema digabung ke commit `BaseAgent`. Test ikut di commit kodenya.
    `ChatbotAgent` dibuat sebelum registry, karena doctest registry memakainya.
  - `list_info()` diganti `list_agents() -> list[BaseAgent]` ditambah `is_available()`. Aturan layer
    melarang `agents/` meng-import `schema/`, jadi konversi ke `AgentInfo` dilakukan di service (F06).
  - Ditambah `ModelFactory.resolve_name()` supaya key cache graph memakai nama model final
    (`None` dan nama default berbagi satu graph).
  - Ditambah `get_agent()` (untuk `parse_config`) dan `DuplicateAgentError`.
  - `agent_id` dan `description` adalah atribut instance (argumen konstruktor), supaya satu class
    seperti `ToolCallingAgent` (F15) bisa didaftarkan beberapa kali dengan ID berbeda.
  - Agent default untuk `/info` belum ditentukan di sini. Keputusannya ada di F06.
- **Acceptance criteria:**
  - [x] Agent yang `load()`-nya gagal tidak menghentikan registry.
  - [x] Model berbeda menghasilkan graph berbeda (FR-4).
  - [x] `parse_config` menolak key yang tidak dikenal untuk agent tanpa config custom.
- **Squash title:** `feat(agents): add agent registry and chatbot agent (F05)`

### F06: Service app

- **Branch:** `feature/F06-service-app`
- **FR:** FR-3, FR-5, FR-10, FR-11, FR-15, NFR-6
- **File:** `service/app.py` (`create_app`, lifespan), `service/auth.py` (`verify_bearer`),
  `service/errors.py` (exception handler), `service/routes/info.py`, `run_service.py`,
  `tests/service/`
- **Catatan desain:**
  - Lifespan membuat objek berurutan: `Settings` → `ModelFactory` → `CheckpointerProvider` →
    `AgentRegistry.load_all()`. Hasilnya disimpan di `app.state`.
  - Handler memetakan error: `AgentNotFoundError` → 404, `UnknownModelError` → 422,
    `AgentUnavailableError` → 503.
  - `/health` didaftarkan di luar router yang dilindungi auth.
  - `/info` menyertakan `config_schema` (JSON Schema) milik setiap agent (FR-27).
- **Referensi lama:** `service/service.py` (`lifespan`, `verify_bearer`, `/info`), dan
  `run_service.py` (event loop selector di Windows).
- **Rencana commit:**
  1. `feat(agents): add default agent catalog`
  2. `feat(service): add app factory with lifespan wiring`
  3. `feat(service): add optional bearer auth dependency`
  4. `build: use importlib import mode for pytest`
  5. `feat(service): map domain errors to http status codes`
  6. `feat(service): add health and info endpoints`
  7. `fix(agents): give EmptyAgentConfig an explicit public description`
  8. `feat(service): add run_service entrypoint`
  9. `docs: record F06 service app decisions`
- **Penyesuaian saat implementasi:**
  - Keputusan user: agent default `chatbot` (konstanta `DEFAULT_AGENT_ID` di `agents/catalog.py`,
    bukan env var). Error validasi 422 memakai list per field bawaan FastAPI, dan NFR-6 direvisi.
  - `create_app(settings=None, agents=None, default_agent_id=...)` bisa di-inject untuk test.
    `default_agent_id` yang tidak terdaftar langsung gagal saat app dibuat.
  - Lifespan juga menyimpan `ModelFactory` di `app.state` (untuk `default_model` di `/info`).
    Akses `app.state` lewat dependency bertipe di `service/dependencies.py`.
  - `ModelNotConfiguredError` → 503. Exception lain → 500 dengan detail generik dan traceback di log.
  - `/info` hanya menampilkan agent yang tersedia. `agent_to_info` ada di `service/converters.py`.
  - Ditambah schema `HealthStatus`.
  - pytest memakai `--import-mode=importlib`, karena `tests/agents/test_errors.py` dan
    `tests/service/test_errors.py` bentrok di mode default.
  - Event loop policy Windows dari toolkit lama tidak di-port (hanya dibutuhkan psycopg).
- **Acceptance criteria:**
  - [x] Test dengan `httpx.AsyncClient` + `ASGITransport`.
  - [x] `AgentNotFoundError` dari route mana pun menjadi 404 berformat `{"detail": ...}` (dites
        lewat route dummy di test).
  - [x] `/health` lolos tanpa token walaupun `AUTH_SECRET` diset.
- **Squash title:** `feat(service): add fastapi app, auth, health and info (F06)`

### F07: Invoke & history

- **Branch:** `feature/F07-invoke-history`
- **FR:** FR-6, FR-8, FR-12, FR-13, FR-14, FR-27
- **File:** `service/run_input.py` (`RunInputBuilder`, `InvalidAgentConfigError` → 422),
  `service/converters.py`
  (`langchain_to_chat_message`, `messages_from_state`), `service/routes/invoke.py`,
  `service/routes/history.py`, `tests/service/`
- **Catatan desain:**
  - `RunInputBuilder.build(user_input, agent) -> RunInput` (config, input atau
    `Command(resume=...)`, `run_id` uuid7). Pengecekan interrupt dipisah ke method privat agar
    nesting tetap ≤ 2.
  - Converter ditulis sebagai function karena berupa transformasi murni (lihat AGENTS.md
    § Class vs Function).
- **Referensi lama:** `service/service.py` (`_handle_input`, `invoke`, `history`), dan
  `service/utils.py:42` (`langchain_to_chat_message`), `:82` (`messages_from_checkpoint`).
- **Rencana commit:**
  1. `feat(service): add message converters from langchain to api schema`
  2. `feat(service): add thread ownership check from checkpoint metadata`
  3. `feat(service): build run input with config validation and resume`
  4. `feat(schema): add thread and user id header names`
  5. `feat(service): add invoke endpoint`
  6. `fix(llm): return a fresh message from FakeModel on every call`
  7. `feat(service): add history endpoint`
  8. `docs: record F07 invoke and history decisions`
- **Penyesuaian saat implementasi:**
  - Keputusan user: ID thread/user dikembalikan lewat header `X-Thread-Id`/`X-User-Id`
    (`schema/headers.py`), bukan field di `ChatMessage`. `/invoke` juga mengecek pemilik thread
    (FR-28 baru), bukan hanya `/history`.
  - `RunInputBuilder` ditulis sebagai function `build_run_input` (tanpa state, aturan praktis
    AGENTS.md). Commit validasi config digabung ke sini.
  - Config tidak valid dilempar sebagai `RequestValidationError` dengan `loc` diawali
    `("body", "agent_config")`, sehingga format 422-nya sama dengan error body lain.
    `InvalidAgentConfigError` tidak dibuat.
  - Ditambah `service/thread_access.py` (`ThreadNotFoundError` → 404, `ensure_thread_owner`).
  - Converter: `messages_from_state` menjadi `state_to_chat_messages`, ditambah
    `final_chat_message` dan `interrupt_to_chat_message`. Fallback `__previous__` (functional API)
    tidak di-port.
  - Bug `FakeModel` dari F02 ditemukan lewat test history dan diperbaiki: respons kini disalin di
    setiap panggilan.
- **Acceptance criteria:**
  - [x] Thread yang sedang interrupt menerima `Command(resume=...)` (dites dengan agent fake).
  - [x] `thread_id` kosong diisi otomatis dan dikembalikan.
  - [x] `agent_config` yang tidak valid menghasilkan 422 beserta nama field yang salah. Config
        yang valid sampai ke node graph lewat `configurable`.
- **Squash title:** `feat(service): add invoke and history endpoints (F07)`

### F08: SSE streaming

- **Branch:** `feature/F08-sse-streaming`
- **FR:** FR-7, PRD §7.3
- **File:** `service/streaming.py` (`StreamService`, `SseFormatter`), `service/routes/stream.py`,
  `tests/service/test_streaming.py`
- **Catatan desain:**
  - `StreamService.stream(run_input) -> AsyncIterator[str]`. Satu method privat per jenis event:
    `_handle_updates`, `_handle_message_chunk`, `_handle_custom`.
  - `try/finally` menjamin `[DONE]` selalu terkirim. Satu-satunya `except Exception` yang diizinkan
    ada di sini (batas sistem): di-log dengan `logger.exception` lalu dikirim sebagai frame
    `error`.
  - Echo pesan human di-skip. Node bertag `skip_stream` tidak menghasilkan token.
- **Referensi lama:** `service/service.py:243-353`. Ini contoh yang **tidak boleh** ditiru (nesting
  6+, deteksi berbasis string di `:282`).
- **Rencana commit:**
  1. `feat(service): add sse frame formatting for stream events`
  2. `feat(service): add StreamService handling updates and message chunks`
  3. `feat(service): add stream endpoint`
  4. `docs: record F08 streaming decisions`
- **Penyesuaian saat implementasi:**
  - `SseFormatter` ditulis sebagai function `sse_frame` + konstanta `DONE_FRAME` (transformasi
    murni). `StreamService` dibuat per request, karena graph/run/opsi token dipakai bersama oleh
    beberapa handler.
  - `StreamService(graph, run, stream_tokens).stream()`, bukan `stream(run_input)`. Validasi
    (`build_run_input`) terjadi di route sebelum response dimulai, jadi request salah tetap 404/422
    JSON.
  - `[DONE]` di-yield setelah blok `try/except`, bukan di `finally`, supaya client yang putus tidak
    memicu `RuntimeError` saat `GeneratorExit`.
  - Echo human dibuang berdasarkan tipe (`HumanMessage`), bukan pencocokan isi seperti kode lama.
  - `subgraphs=True` dan penanganan supervisor belum ada (F17).
  - Test error di tengah stream ikut di commit `StreamService`.
- **Acceptance criteria:**
  - [x] Urutan frame sesuai PRD §7.3.
  - [x] Nesting ≤ 2 di semua method.
  - [x] Ada test untuk error di tengah stream.
- **Squash title:** `feat(service): add sse streaming endpoint (F08)`

### F09: User threads

- **Branch:** `feature/F09-user-threads`
- **FR:** FR-9
- **File:** `service/threads.py` (`ThreadRepository`), `service/routes/threads.py`,
  `tests/service/test_threads.py`
- **Catatan desain:** port logika dan **konstanta bernama** dari kode lama (`THREAD_HEAD_STEP`,
  `MAX_THREAD_HEADS`, `TITLE_MAX_LENGTH`, dll.), termasuk cek ulang metadata `user_id` agar thread
  tidak bocor antar user.
- **Referensi lama:** `service/threads.py` (pola yang baik, konstanta di `:21-32`).
- **Rencana commit:**
  1. `feat(service): add ThreadRepository listing threads per user`
  2. `feat(service): add threads endpoint with limit validation`
  3. `docs: record F09 user threads decisions`
- **Penyesuaian saat implementasi:**
  - Test isolasi ikut di commit kodenya, jadi tidak ada commit `test(service)` terpisah.
  - "Paginasi" berarti `limit` saja (sesuai `UserThreadsQuery` dari F04). Tidak ada cursor/offset.
  - Listing juga difilter per `agent_id`, bukan hanya `user_id`.
  - Thread tanpa message human berjudul `DEFAULT_THREAD_TITLE` ("Untitled thread"), karena
    `ThreadSummary.title` wajib berupa string.
  - `ThreadRepository` dibuat sekali di lifespan (`app.state.thread_repository`). Ukuran halaman
    dan batas scan menjadi argumen konstruktor supaya paging bisa dites.
  - Agent tidak dikenal → 404. Agent unavailable tetap bisa didaftar thread-nya (listing tidak
    butuh graph).
- **Acceptance criteria:**
  - [x] User A tidak bisa melihat thread milik user B.
  - [x] `limit` di luar 1–100 menghasilkan 422.
- **Squash title:** `feat(service): add user threads endpoint (F09)`

### F18: Thread rename & delete

- **Branch:** `feature/F18-thread-management`
- **FR:** FR-25, FR-26
- **File:** `memory/thread_metadata.py` (`ThreadMetadataRepository`, tabel `thread_metadata` di
  file SQLite yang sama), `service/threads.py` (`ThreadService`: rename, delete, dan merge judul
  custom ke listing), route `PATCH`/`DELETE` di `service/routes/threads.py`, `tests/`
- **Catatan desain:**
  - Kepemilikan dicek lewat metadata checkpoint (`user_id`). Thread yang bukan milik user → 404,
    bukan 403, supaya keberadaan thread tidak bocor.
  - Delete memanggil `checkpointer.adelete_thread(thread_id)` lalu menghapus baris metadata.
  - Panjang judul dibatasi `TITLE_MAX_LENGTH` (konstanta yang sama dengan F09).
  - Bergantung pada F03 (koneksi SQLite) dan F09 (listing).
- **Rencana commit:**
  1. `feat(memory): add ThreadMetadataRepository for custom thread titles`
  2. `refactor(service): check thread ownership from checkpoint metadata`
  3. `feat(service): add thread rename endpoint with ownership check`
  4. `feat(service): add thread delete endpoint removing checkpoints`
  5. `feat(service): show custom titles in thread listing`
  6. `docs: record F18 thread management decisions`
- **Penyesuaian saat implementasi:**
  - `ThreadService` tidak dibuat terpisah. Rename/delete ditambahkan ke `ThreadRepository` dari F09,
    yang kini juga menerima `ThreadMetadataRepository`.
  - `ThreadMetadataRepository` memakai koneksi `aiosqlite` sendiri ke file SQLite yang sama, bukan
    koneksi saver. `aiosqlite` kini menjadi dependency eksplisit.
  - Tabel `thread_metadata` hanya berisi `thread_id` dan `title`. Kepemilikan tetap dicek dari
    metadata checkpoint, dan rename tidak mengubah urutan listing.
  - Kepemilikan juga mencakup `agent_id`, sama dengan F07. `ensure_thread_owner` kini menerima
    metadata checkpoint (bukan `StateSnapshot`), dan `is_thread_owner` dipakai bersama listing.
  - Ditambah varian agent default `PATCH/DELETE /threads/{thread_id}`.
  - Setelah delete, `/history` menjawab 404 (thread tidak ada), bukan riwayat kosong.
- **Acceptance criteria:**
  - [x] Setelah rename, judul baru muncul di `GET /threads`.
  - [x] Setelah delete, `/history` thread tersebut menjawab 404 dan thread hilang dari listing.
  - [x] User B mendapat 404 saat rename/delete thread milik user A.
- **Squash title:** `feat(service): add thread rename and delete endpoints (F18)`

### F10: Architecture docs

- **Branch:** `feature/F10-docs-architecture`
- **File:** `docs/ARCHITECTURE.md`. Update link di README dan AGENTS.
- **Isi:** alur request (router → `RunInputBuilder` → `AgentRegistry` → graph → checkpointer →
  `StreamService`), diagram layer, siklus hidup lifespan, dan cara menambah agent.
- **Rencana commit:**
  1. `docs: add architecture overview with request flow`
  2. `docs: link architecture doc from readme and agents guide`
  3. `docs: record F10 and v0.1.0 release steps`
- **Penyesuaian saat implementasi:**
  - Dibuat sebagai stacked branch di atas `feature/F08-sse-streaming`, karena dokumen ini
    menjelaskan `StreamService` dan keduanya mengubah ROADMAP/memory.
  - Nama di dokumen mengikuti kode sebenarnya (`build_run_input`, `ThreadRepository`,
    `ThreadMetadataRepository`), bukan nama rencana awal (`RunInputBuilder`).
  - Ditambah bagian kepemilikan thread, tabel error, persistence, dan testing.
- **Squash title:** `docs: add architecture documentation (F10)`
- **Setelah merge:** rilis **v0.1.0**.

---

## M2: Client + UI → v0.2.0

### F11: Agent client

- **Branch:** `feature/F11-agent-client`
- **FR:** FR-17, FR-18, FR-19
- **File:** `client/client.py` (`AgentClient`), `client/sse.py` (`SseParser`), `client/errors.py`
  (`AgentClientError`), `tests/client/`
- **Catatan desain:**
  - Satu `_build_payload` dan satu `_headers` dipakai bersama oleh method sync dan async.
  - Tidak ada request di `__init__`. `info` diambil lazy lalu di-cache.
  - Menangkap `httpx.HTTPStatusError` dan `httpx.RequestError` secara spesifik.
- **Referensi lama:** `client/client.py` (duplikasi payload di `:111`, `:157`, `:234`, `:291`).
- **Rencana commit:**
  1. `feat(client): add SseParser and AgentClientError`
  2. `feat(client): add sync AgentClient methods`
  3. `feat(client): add async AgentClient methods`
  4. `fix(llm): enable token streaming for openai-compatible models`
  5. `docs: record F11 agent client decisions`
- **Penyesuaian saat implementasi:**
  - Keputusan user: `invoke` → `AgentReply(message, thread_id, user_id)`, `stream`/`astream` →
    context manager `StreamRun`/`AsyncStreamRun` dengan `thread_id`/`user_id`. Frame `error`
    di-yield sebagai `ErrorEvent`.
  - Tidak ada `_headers`: token bearer dipasang sekali di client httpx. `auth_secret` diberikan
    eksplisit karena `client/` tidak boleh membaca env/`core/`. Request dibangun sekali sebagai
    `RequestSpec` (`client/requests.py`) untuk sync dan async.
  - Ditambah `rename_thread`/`delete_thread` (dibutuhkan F13). `agent_id=None` memakai route agent
    default.
  - `httpx` dipindah dari dev ke dependency runtime. Ditambah `tests/client/test_layering.py`.
  - Selain `MockTransport`, ada test kontrak client vs app asli lewat `httpx.ASGITransport`
    (in-process, tanpa server).
  - Smoke test dengan LLM asli menemukan bug F02: `ChatOpenAI` tanpa `streaming=True` hanya
    mengirim satu chunk ke `/stream`. Diperbaiki di commit `fix(llm)`.
- **Acceptance criteria:**
  - [x] Semua test memakai `httpx.MockTransport` atau `ASGITransport` (tanpa server).
- **Squash title:** `feat(client): add sync and async agent client (F11)`

### F12: UI chat

- **Branch:** `feature/F12-ui-chat`
- **FR:** FR-20, FR-24
- **File:** `ui/app.py` (entrypoint), `ui/settings.py` (`UiSettings`), `ui/chat_view.py`
  (`ChatView`), `ui/message_renderer.py` (`MessageRenderer`), `tests/ui/`
  (`streamlit.testing.AppTest`)
- **Catatan desain:** `MessageRenderer` punya satu method per tipe pesan (human, ai, tool call).
  `ui/` hanya boleh import `client/` dan `schema/`.
- **Referensi lama:** `streamlit_app.py:67-525`. Ini contoh yang **tidak boleh** ditiru (`main`
  ±300 baris, nesting ±7).
- **Rencana commit:**
  1. `feat(ui): add UiSettings and streamlit entrypoint`
  2. `feat(ui): add MessageRenderer for human, ai and tool messages`
  3. `feat(ui): add ChatView with token streaming`
  4. `docs: record F12 ui chat decisions`
- **Penyesuaian saat implementasi:**
  - Ditambah `ui/session.py` (`ChatSession`, dataclass bertipe di `st.session_state`) sebagai
    pengganti key `session_state` yang tersebar.
  - `thread_id`/`user_id` diambil dari header respons stream setelah giliran pertama, dan baru
    disimpan di session browser. Penyimpanan di URL dikerjakan di F13 (FR-22).
  - UI selalu men-stream ke agent default. Toggle streaming dan pemilih agent/model ada di F13.
  - Test memakai `AppTest` dengan `AgentClient` asli + `httpx.MockTransport` yang disuntikkan lewat
    `st.session_state[CLIENT_OVERRIDE_KEY]`. Ditambah `tests/ui/test_layering.py`.
  - Teks yang tampil ke user (placeholder input, label tool) ditulis dalam bahasa Inggris,
    konsisten dengan pesan error API.
- **Squash title:** `feat(ui): add streamlit chat view with streaming (F12)`

### F13: UI sidebar & threads

- **Branch:** `feature/F13-ui-sidebar-threads`
- **FR:** FR-21, FR-22, FR-25, FR-26 (sisi UI)
- **File:** `ui/sidebar_view.py` (`SidebarView`), `ui/url_state.py` (`UrlState`), `tests/ui/`
- **Catatan desain:** TTL cache daftar thread memakai konstanta `THREAD_LIST_CACHE_TTL_SECONDS`,
  bukan literal `600` seperti di kode lama.
- **Referensi lama:** `streamlit_app.py` (sidebar, query param, `@st.cache_data(ttl=600)` di
  `:56`).
- **Rencana commit:**
  1. `feat(ui): add UrlState for user, thread and agent query params`
  2. `feat(ui): add SidebarView with agent and model pickers`
  3. `feat(ui): list previous threads in sidebar`
  4. `feat(ui): add rename and delete actions for threads`
  5. `docs: record F13 sidebar decisions`
- **Penyesuaian saat implementasi:**
  - Keputusan user: `user_id` ikut disimpan di URL (FR-22 direvisi), karena thread hanya bisa dibuka
    oleh pemiliknya.
  - `AgentClient` dibuat per session browser (bukan `st.cache_resource`), karena `agent_id` client
    mengikuti pilihan agent masing-masing browser.
  - Toggle streaming dipetakan ke `stream_tokens=False`, bukan beralih ke `invoke`, supaya tool call
    tetap tampil.
  - Mengganti agent memulai thread baru. Agent di URL yang tidak dikenal diganti agent default.
    Thread di URL yang tidak ada (404) diganti chat baru.
  - Thread baru langsung muncul di sidebar lewat `st.rerun()` setelah run tanpa error.
  - `THREAD_LIST_CACHE_TTL_SECONDS = 300`, dan cache dihapus setiap kali UI mengubah daftar thread.
- **Squash title:** `feat(ui): add sidebar with thread history and pickers (F13)`

### F14: Docker Compose & e2e

- **Branch:** `feature/F14-compose-e2e`
- **File:** `docker/Dockerfile` (target `service` dan `ui`), `.dockerignore`, `compose.yaml`,
  `compose.llm.yaml`, `tests/integration/test_compose_e2e.py` (marker `integration`), job CI `e2e`,
  update README.
- **Catatan desain:** Compose memakai `USE_FAKE_MODEL=true` secara default supaya e2e berjalan
  tanpa API key. Healthcheck memanggil `/health`.
- **Referensi lama:** `docker/Dockerfile.service`, `docker/Dockerfile.app`, `compose.yaml`.
- **Rencana commit:**
  1. `build(docker): add service and ui image targets`
  2. `build(docker): add compose with healthcheck and fake model default`
  3. `test(service): add compose end-to-end smoke test`
  4. `docs: document docker compose usage`
- **Penyesuaian saat implementasi:**
  - Satu Dockerfile multi-target, bukan dua file. Layer dependency dibangun dan di-cache sekali.
  - Kedua image memasang dependency yang sama (sekitar 1 GB, layer dipakai bersama), karena
    `pyproject.toml` belum memisahkan dependency service dan UI. Pemisahan lewat extras dicatat
    sebagai optimasi nanti.
  - Konfigurasi service ditulis eksplisit di `compose.yaml` (bukan `env_file: .env`), karena
    `LLM_BASE_URL` di `.env` developer bisa mengarah ke `localhost`. Ditambah `compose.llm.yaml`
    untuk LLM asli (`DOCKER_LLM_BASE_URL`, `host.docker.internal`).
  - Container berjalan non-root, SQLite di volume `/data`, dan healthcheck memakai Python.
  - Test e2e menjalankan UI asli dengan `AppTest` di dalam container UI. Ditambah job CI `e2e`.
- **Acceptance criteria:**
  - [x] `docker compose up` berjalan, lalu chat di UI mendapat balasan dari FakeModel (diverifikasi
        lewat `AppTest` di container UI; klik di browser tidak diotomasi).
- **Squash title:** `build(docker): add compose stack and e2e smoke test (F14)`
- **Setelah merge:** rilis **v0.2.0**.

---

## M3: Agent Tambahan → v0.3.0

### F19: Reasoning display

- **Branch:** `feature/F19-reasoning-display`
- **FR:** FR-29
- **Latar belakang:** model reasoning (misalnya Qwen3 lewat Ollama) menulis token pemikiran di field
  stream terpisah, bukan `content`. `ChatOpenAI` membuang field non-standar itu, sehingga selama
  model berpikir `/stream` tidak mengirim frame apa pun dan UI tampak idle.
- **Langkah 1 (klarifikasi, sebelum menulis kode):**
  - Ukur stream mentah endpoint yang dipakai: nama field reasoning (`reasoning` atau
    `reasoning_content`) dan waktunya sebelum `content` dimulai. Script probe pernah dibuat untuk
    ini, berupa `httpx.stream` ke `{LLM_BASE_URL}/chat/completions` dengan mencatat field per delta.
  - Putuskan bersama user: apakah reasoning disimpan di riwayat dan tampil saat thread dibuka ulang
    (PRD §11 no. 5).
- **File:** `llm/reasoning.py` (subclass `ChatOpenAI` yang menyalin field reasoning ke
  `additional_kwargs`), `llm/factory.py`, `llm/fake.py` (reasoning bisa di-script),
  `schema/stream.py` (`ReasoningEvent`), `schema/responses.py` (`ChatMessage.reasoning`, jika
  disimpan), `service/streaming.py`, `service/converters.py`, `ui/message_renderer.py`, `tests/`.
- **Catatan desain:**
  - Tetap satu jalur OpenAI-compatible (scope v1). Bukan menambah provider baru seperti
    `langchain-ollama`.
  - Event SSE baru `{"type": "reasoning", "content": "..."}` dikirim sebelum token jawaban. Ini
    perubahan kontrak: service dan client (yang memakai `STREAM_EVENT_ADAPTER` yang sama) dirilis
    bersama. Client versi lama akan menolak frame ini.
  - `stream_tokens=False` juga mematikan frame `reasoning`.
  - UI menampilkan reasoning di blok "Thinking" (`st.status`/expander) yang terbuka selama model
    berpikir, lalu tertutup saat jawaban mulai mengalir.
  - Model tanpa reasoning (dan `FakeModel` default) tidak berubah perilakunya.
- **Rencana commit:**
  1. `feat(llm): keep reasoning from openai-compatible streams`
  2. `feat(schema): add reasoning stream event`
  3. `feat(service): stream reasoning before answer tokens`
  4. `feat(ui): show reasoning in a collapsible thinking block`
  5. `docs: record F19 reasoning decisions`
- **Acceptance criteria:**
  - [x] Dengan `FakeModel` yang di-script berisi reasoning, `/stream` mengirim frame `reasoning`
        sebelum `token`, dan UI menampilkan blok "Thinking" sebelum jawaban.
  - [x] Smoke test dengan model reasoning asli: frame `reasoning` muncul selama jeda yang
        sebelumnya kosong (qwen3.5:9b: reasoning pertama di detik 3,7, token pertama di detik 9,8).
  - [x] Model tanpa reasoning menghasilkan urutan frame yang sama seperti sebelum F19.
  - [x] Test kontrak client vs service mencakup frame `reasoning`.
- **Penyesuaian saat implementasi:**
  - Hasil ukur langkah 1: Ollama mengirim field `reasoning` (vLLM/DeepSeek memakai
    `reasoning_content`). Keduanya diterima, lalu disimpan sebagai
    `additional_kwargs["reasoning_content"]`.
  - Keputusan user (open question 5): reasoning disimpan di riwayat. `ChatMessage.reasoning`
    diisi di `/invoke`, `/history`, dan frame `message` akhir, lalu UI menampilkannya tertutup saat
    thread dibuka ulang.
  - Tidak ada perubahan kode di client. `SseParser` sudah menerima event baru lewat
    `STREAM_EVENT_ADAPTER`.
  - `skip_stream` juga menyembunyikan reasoning.
  - Temuan: model reasoning bisa berpikir sangat lama (sekali lebih dari 300 detik untuk prompt
    singkat), karena belum ada batas token jawaban. Dicatat sebagai kandidat fitur berikutnya.
- **Squash title:** `feat(llm): stream and display model reasoning (F19)`

### F15: Research assistant

- **Branch:** `feature/F15-research-assistant`
- **FR:** PRD §5 Agent v1
- **File:** `agents/tool_calling.py` (`ToolCallingAgent`), `agents/tools/web_search.py`,
  `agents/tools/calculator.py`, register `research-assistant`, `tests/agents/`
- **Catatan desain:**
  - `ToolCallingAgent(agent_id, description, tools, system_prompt)`. RAG nantinya cukup menjadi
    instance lain dari class ini.
  - Konstanta `MIN_REMAINING_STEPS`, bukan literal `2`.
  - Tanggal dihitung di dalam node, bukan saat import.
  - Tool ditulis sebagai function `@tool` (lihat AGENTS.md § Class vs Function).
- **Referensi lama:** `agents/research_assistant.py` (`:39` tanggal yang basi, `:75` magic number),
  `agents/tools.py`.
- **Rencana commit:**
  1. `feat(agents): add calculator tool backed by numexpr`
  2. `feat(agents): add duckduckgo web search tool`
  3. `feat(agents): add configurable ToolCallingAgent`
  4. `feat(agents): register research-assistant agent`
  5. `docs: record F15 research assistant decisions`
- **Penyesuaian saat implementasi:**
  - Web search memakai package `ddgs` langsung (bukan `langchain-community`). Tool dibuat oleh
    factory `create_web_search_tool(backend)` dengan `SearchBackend` yang di-inject. Adapter
    `DuckDuckGoSearch` dipakai di produksi, dan pencarian sinkron dijalankan lewat
    `asyncio.to_thread`.
  - `ToolNode(handle_tool_errors=(ToolException,))`: error tool yang diharapkan dikembalikan ke
    model sebagai pesan error, sedangkan bug lain tetap menggagalkan run.
  - Prompt dan factory research assistant ada di `agents/research.py`. Agent default tetap
    `chatbot`.
  - Safeguard Groq dan tool cuaca dari kode lama tidak di-port (di luar scope v1).
  - Smoke test dengan qwen3.5:9b dan DuckDuckGo asli: web_search → calculator → jawaban dalam
    18,5 detik. Model tidak selalu mengutip link walaupun diminta prompt.
- **Acceptance criteria:**
  - [x] Loop tool calling dites dengan `FakeModel`.
  - [x] Tool web search di-mock di unit test.
- **Squash title:** `feat(agents): add research assistant with tool calling (F15)`

### F16: Interrupt agent

- **Branch:** `feature/F16-interrupt-agent`
- **FR:** FR-12, FR-24
- **File:** `agents/interrupt.py` (`InterruptAgent`), `tests/agents/`
- **Catatan desain:** gunakan pola `interrupt()` + validasi lewat loop/edge graph. Tidak ada rekursi
  dan tidak ada `state["messages"].append`. Node mengembalikan dict update.
- **Referensi lama:** `agents/interrupt_agent.py` (rekursi dan mutasi state di `determine_birthdate`).
- **Rencana commit:**
  1. `feat(agents): add InterruptAgent asking for missing input`
  2. `test(agents): cover interrupt and resume through invoke endpoint`
- **Squash title:** `feat(agents): add human-in-the-loop interrupt agent (F16)`

### F17: Supervisor agent

- **Branch:** `feature/F17-supervisor-agent`
- **FR:** FR-4, FR-23
- **File:** `agents/supervisor.py` (`SupervisorAgent`), update `service/streaming.py` (tag
  `subagent` eksplisit), `ui/message_renderer.py` (render bertingkat), `tests/`
- **Catatan desain:**
  - Sub-agent dibuat di `build(model, ...)` sehingga memakai model dari request.
  - Streaming mendeteksi sub-agent lewat tag/metadata, bukan nama node.
- **Referensi lama:** `agents/langgraph_supervisor_agent.py` (`:8` model dibuat saat import),
  `service/service.py:282`.
- **Rencana commit:**
  1. `feat(agents): add SupervisorAgent with math and research sub-agents`
  2. `feat(service): stream sub-agent events using explicit tags`
  3. `feat(ui): render sub-agent handoffs as nested blocks`
- **Squash title:** `feat(agents): add supervisor agent with nested streaming (F17)`
- **Setelah merge:** rilis **v0.3.0**.
