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
| F16 | Interrupt agent | M3 | done |
| F17 | Supervisor agent | M3 | done |
| F20 | Firecrawl web search | M3 | done |
| F21 | LLM token limit | M4 | done |
| F22 | Dependency extras | M4 | done |
| F23 | Postgres migration | M4 | done |
| F24 | User auth & CORS | M4 | done |
| F25 | API contract export | M4 | done |
| F26 | Projects | M5 | done |
| F27 | Context builder | M5 | done |
| F28 | Built-in skills | M5 | done |
| F29 | Context policy | M5 | done |
| F30 | Long-term memory | M5 | done |
| F31 | Evals & tracing | M5 | done |
| F32 | Frontend scaffold & auth | M6 | done |
| F33 | Chat UI | M6 | done |
| F34 | Projects & threads UI | M6 | todo |
| F35 | Artifact storage | M7 | todo |
| F36 | Workspace & file tools | M7 | todo |
| F37 | Sandbox | M7 | todo |
| F38 | Artifact panel UI | M7 | todo |
| F39 | SQL data source | M8 | todo |
| F40 | Data analyst project | M8 | todo |
| F41 | Worker & scheduler | M8 | todo |
| F42 | PDF report & scheduled analysis | M8 | todo |
| F43 | Knowledge ingestion | M9 | todo |
| F44 | Knowledge retrieval | M9 | todo |
| F45 | Knowledge UI | M9 | todo |
| F46 | OpenAI-compatible endpoint | M10 | todo |

## Milestone & Rilis

| Milestone | Fitur | Rilis | Hasil |
|---|---|---|---|
| M0: Bootstrap | F00 | – | Repo, tooling, dan CI siap |
| M1: Core + Service | F01–F10, F18 | `v0.1.0` | API lengkap dengan `chatbot`, dites dengan FakeModel |
| M2: Client + UI | F11–F14 | `v0.2.0` | Chat end-to-end via Docker Compose |
| M3: Agent tambahan | F19, F15–F17, F20 | `v0.3.0` | Reasoning terlihat, tool calling, human-in-the-loop, multi-agent |
| M4: Foundation | F21–F25 | `v0.4.0` | Postgres di compose, login JWT, batas token, image lebih kecil, kontrak API dipublikasikan |
| M5: Harness Core | F26–F31 | `v0.5.0` | Project, prompt dirakit per giliran, skill built-in, context management, memory, eval |
| M6: Frontend | F32–F34 | `v0.6.0` | **Demo showcase:** chat React bergaya Claude dengan Projects |
| M7: Files & Execution | F35–F38 | `v0.7.0` | Artifact, workspace, sandbox, panel artifact |
| M8: Data Analytics | F39–F42 | `v0.8.0` | Analisa SQL → chart, job terjadwal → PDF |
| M9: Knowledge | F43–F45 | `v0.9.0` | RAG per Project dengan ingestion |
| M10: Interop | F46 | `v0.10.0` | Endpoint OpenAI-compatible |

Arsitektur Fase 2 (M4–M10) mengikuti [ADR 0001–0005](adr/README.md).

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
F13 → F14 → *rilis v0.2.0* → F19 → F15 → F16 → F17 → F20 → *rilis v0.3.0*

**Bisa dikerjakan paralel (lebih dari satu developer):**
- F02 ∥ F03 ∥ F04
- F07 ∥ (F09 → F18)
- F11 bisa dimulai setelah F04, karena hanya bergantung pada kontrak dan bisa dites dengan
  `httpx.MockTransport`.
- F15 ∥ M2

### Fase 2 (M4–M10)

```text
F21, F22 (independen)
F23 ─┬─► F24 ─► F25 ─► F32 ─► F33 ─► F34 ─► F38 ─► F45
     ├─► F26 ─► F27 ─┬─► F28 ─► F40
     │               ├─► F29
     │               ├─► F30
     │               └─► F31
     ├─► F35 ─► F36 ─► F37 ─► F40 ─► F42
     ├─► F39 ─► F40
     ├─► F41 ─► F42
     └─► F43 ─► F44 ─► F45
F24, F26 ─► F46
```

Prasyarat tambahan yang tidak terlihat di graph:

- F34 butuh F26 dan F28 (pemilih skill). F38 butuh F35.
- F40 butuh F28 (skill semantic layer), F36, dan F37. F42 butuh F35 dan F41.
- F43 butuh F26, F35, dan F41 (worker untuk ingestion).

**Urutan eksekusi yang disarankan (satu developer):**
F21 → F22 → F23 → F24 → F25 → *rilis v0.4.0* → F26 → F27 → F28 → F29 → F30 → F31 → *rilis v0.5.0* →
F32 → F33 → F34 → *rilis v0.6.0* → F35 → F36 → F37 → F38 → *rilis v0.7.0* → F39 → F40 → F41 → F42 →
*rilis v0.8.0* → F43 → F44 → F45 → *rilis v0.9.0* → F46 → *rilis v0.10.0*

**Bisa dikerjakan paralel:**
- F21 ∥ F22 ∥ F23.
- Track frontend (F32 → F33) bisa dimulai setelah F25, paralel dengan M5. F34 menunggu F26/F28.
- F39 ∥ M7 (tool SQL bisa dites tanpa workspace, dengan hasil sebagai teks).
- F46 kapan pun setelah F26.

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
| FR-30 | F21, F26, F33 | | FR-45 | F32, B3 |
| FR-31 | F22 | | FR-46 | F35 |
| FR-32 | F23 | | FR-47 | F36 |
| FR-33 | F24 | | FR-48 | F36 |
| FR-34 | F24 | | FR-49 | F37 |
| FR-35 | F25 | | FR-50 | F38 |
| FR-36 | F26, F34 | | FR-51 | F39 |
| FR-37 | F27 | | FR-52 | F40 |
| FR-38 | F28, F34 | | FR-53 | F41 |
| FR-39 | F29 | | FR-54 | F42 |
| FR-40 | F30 | | FR-55 | F43 |
| FR-41 | F31 | | FR-56 | F44 |
| FR-42 | F32 | | FR-57 | F45 |
| FR-43 | F33 | | FR-58 | F46 |
| FR-44 | F34 | | | |

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

   Mulai F23, test database butuh Postgres (`docker compose up -d postgres`). Mulai F32, jika
   `frontend/` berubah, jalankan juga lint, type check, dan test frontend (perintahnya ditetapkan
   di F32). Jika schema API berubah, generate ulang kontrak (F25).

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
  3. `docs: record F16 interrupt agent decisions`
- **Penyesuaian saat implementasi:**
  - Contoh zodiak dari kode lama dipertahankan. Graph: `START → (birthdate ada?) → respond`, atau
    `extract_birthdate → (valid?) → respond`, atau `ask_birthdate (interrupt) → extract_birthdate`.
  - Ekstraksi memakai `with_structured_output(..., method="function_calling")` bertag
    `skip_stream`. Validasi tanggal (format, tanggal di masa depan) dan perhitungan zodiak dilakukan
    di kode, bukan oleh model.
  - Tanggal lahir disimpan di state thread (checkpoint), bukan di Store (Store di luar scope v1).
    Giliran berikutnya di thread yang sama tidak bertanya lagi.
  - Pertanyaan interrupt ditulis model dalam bahasa user, dengan fallback konstanta berbahasa
    Inggris.
  - Node `background` dari kode lama tidak di-port.
- **Acceptance (smoke test qwen3.5:9b):** "Apa zodiak saya?" → bertanya, "bulan Mei" → bertanya
  lagi, "17 Mei 1990" → Taurus, lalu pertanyaan lanjutan dijawab tanpa interrupt.
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
  1. `feat(agents): let ToolCallingAgent run as a stateless sub-agent`
  2. `feat(agents): add SupervisorAgent with math and research sub-agents`
  3. `feat(service): stream sub-agent events using explicit tags`
  4. `feat(ui): render sub-agent handoffs as nested blocks`
  5. `feat(agents): stream expert steps while the expert works`
  6. `fix(agents): ask supervisor to delegate dependent tasks in order`
  7. `docs: record F17 supervisor decisions`
- **Penyesuaian saat implementasi:**
  - Tanpa dependency `langgraph-supervisor`. Graph sendiri: `supervisor` (LLM dengan tool
    delegasi `ask_<expert>`) ⇄ `delegate` (menjalankan `ToolCallingAgent.build_stateless(model)`
    milik expert).
  - Penanda eksplisit: message expert diberi `additional_kwargs["subagent"]` (tersimpan di
    checkpoint) dan menjadi `ChatMessage.agent`. Run expert diberi tag `subagent`. Supervisor hanya
    melihat message tanpa penanda.
  - Langkah expert dikirim bertahap lewat `get_stream_writer()` (mode `custom`), dan
    `StreamService` membuang duplikat berdasarkan `id` message.
  - UI: kontainer berbingkai per expert, karena Streamlit tidak mengizinkan expander bersarang.
  - Smoke test qwen3.5:9b + DuckDuckGo: research_expert → 1991, math_expert → `2026 - 1991 = 35`,
    dengan langkah expert tiba bertahap.
- **Squash title:** `feat(agents): add supervisor agent with nested streaming (F17)`
- **Setelah merge:** F20, lalu rilis **v0.3.0**.

### F20: Firecrawl web search

- **Branch:** `feature/F20-firecrawl-web-search`
- **Latar belakang:** saat smoke test F17, DuckDuckGo gagal beberapa kali berturut-turut. User memilih
  Firecrawl (akun free tier dengan API key).
- **File:** `core/settings.py` (`firecrawl_api_key`), `agents/tools/web_search.py`
  (`SearchBackend` async, `FirecrawlSearch`, `UnconfiguredSearch`, `create_search_backend`),
  `agents/research.py`, `agents/supervisor.py`, `agents/catalog.py`, `service/app.py`
  (`build_search_backend`), `compose.yaml`, `.env.example`, `tests/`.
- **Catatan desain:**
  - REST API langsung (`POST https://api.firecrawl.dev/v2/search`, `{query, limit}`, bearer key)
    dengan `httpx.AsyncClient` yang dipakai ulang. Tidak ada SDK tambahan, dan tidak perlu thread.
    Hanya hasil web (`data.web[]`: `url`, `title`, `description`), tanpa scraping, supaya hemat
    kredit.
  - Keputusan user: tanpa key, agent tetap berjalan. `UnconfiguredSearch` membuat tool menjawab
    "not configured", dan startup mencatat warning.
  - Key mengalir `Settings` → `create_app` → katalog agent → tool. `agents/` tidak membaca env.
  - `ddgs` dihapus dari dependency.
- **Rencana commit:**
  1. `feat(core): add FIRECRAWL_API_KEY setting`
  2. `feat(agents): replace duckduckgo web search with firecrawl`
  3. `feat(service): pass firecrawl search backend from settings to agents`
  4. `docs: switch web search docs to firecrawl`
- **Acceptance criteria:**
  - [x] Request ke Firecrawl (URL, header, body) dan parsing respons dites dengan `MockTransport`.
  - [x] Error 401/402/429/500, koneksi gagal, dan JSON rusak menjadi pesan error untuk model.
  - [x] Tanpa key: service start, warning tercatat, dan agent menjawab tanpa pencarian (smoke test
        dengan qwen3.5:9b).
  - [ ] Smoke test dengan key Firecrawl asli (menunggu user mengisi `FIRECRAWL_API_KEY`).
- **Squash title:** `feat(agents): switch web search to firecrawl (F20)`
- **Setelah merge:** rilis **v0.3.0**.

---

## M4: Foundation → v0.4.0

### F21: LLM token limit

- **Branch:** `feature/F21-llm-token-limit`
- **FR:** FR-30
- **File:** `core/settings.py` (`llm_max_tokens`), `llm/factory.py`, `llm/fake.py` (`finish_reason`
  bisa di-script), `schema/responses.py` (`ChatMessage.truncated`), `service/converters.py`,
  `ui/message_renderer.py`, `tests/`
- **Langkah 1 (klarifikasi):** ukur dengan `qwen3.5:9b` lewat Ollama apakah token reasoning ikut
  dihitung dalam `max_tokens`, dan berapa batas minimum supaya jawaban tidak kosong. Hasilnya
  menentukan nilai default.
- **Catatan desain:**
  - Konstanta `DEFAULT_LLM_MAX_TOKENS`. `ModelFactory.create(name, max_tokens=None)`, dan kunci cache
    mencakup `max_tokens` (override per Project di F26).
  - `finish_reason == "length"` di `response_metadata` diubah converter menjadi
    `ChatMessage.truncated = true`.
- **Rencana commit:**
  1. `feat(core): add LLM_MAX_TOKENS setting`
  2. `feat(llm): pass max tokens to openai-compatible models`
  3. `feat(schema): mark truncated ai messages`
  4. `feat(service): flag messages stopped by the token limit`
  5. `feat(ui): warn when an answer is truncated`
  6. `docs: record F21 token limit decisions`
- **Penyesuaian saat implementasi:**
  - `FakeModel` tidak mendapat field baru. `finish_reason` di-script lewat `response_metadata`
    `AIMessage` respons, dan dikirim sebagai satu chunk penutup saat streaming (string metadata
    digabung LangChain antar chunk, jadi tidak boleh berulang). Perubahan ini masuk commit 2.
  - Hasil ukur Langkah 1 (Ollama 0.40.2, `qwen3.5:9b`): token reasoning **ikut dihitung**. Tanpa
    batas, jawaban memakai 442–3265 token (sapaan hingga penjelasan quicksort dengan kode), jadi
    default `DEFAULT_LLM_MAX_TOKENS = 8192`. Dengan batas 200–300, seluruh token habis untuk
    reasoning dan jawabannya kosong (`finish_reason = "length"`).
  - `ChatOpenAI` (langchain-openai 1.7) selalu mengirim `max_completion_tokens`, dan **Ollama
    mengabaikannya** (762 token keluar walau batasnya 200). Keputusan user: env baru
    `LLM_MAX_TOKENS_PARAM` (`max_tokens` default, atau `max_completion_tokens` untuk model
    reasoning OpenAI). `ReasoningChatOpenAI._get_request_payload` mengganti nama field. Perubahan
    ini masuk commit 1 (setting) dan commit 2 (llm).
- **Acceptance criteria:**
  - [x] `FakeModel` dengan `finish_reason="length"` menghasilkan `truncated=true` di `/invoke`,
        frame `message` `/stream`, dan `/history`.
  - [x] Smoke test dengan model reasoning asli dan batas kecil: peringatan muncul di UI.
        (`LLM_MAX_TOKENS=300`: `/invoke`, frame `message` `/stream`, dan `/history` berisi
        `truncated=true`, dan app Streamlit menampilkan peringatan di kedua jawaban.)
- **Squash title:** `feat(llm): add answer token limit and truncation flag (F21)`

### F22: Dependency extras

- **Branch:** `feature/F22-dependency-extras`
- **FR/NFR:** FR-31, NFR-12
- **File:** `pyproject.toml`, `uv.lock`, `docker/Dockerfile`, `.github/workflows/ci.yml`,
  `.pre-commit-config.yaml` (jika perlu), `README.md`
- **Catatan desain:**
  - Dependency dasar hanya untuk `schema/` + `client/` (pydantic, httpx). Extras: `service`
    (fastapi, uvicorn, langgraph, langchain-*, numexpr, database) dan `ui` (streamlit). Extras
    `analytics` dan `rag` ditambahkan oleh fitur yang pertama kali membutuhkannya.
  - Dev dan CI: `uv sync --all-extras`. Docker: `uv sync --frozen --no-dev --extra <target>`.
  - Ukur ukuran image sebelum dan sesudah (`docker images`), lalu catat di PR dan memory.md.
- **Rencana commit:**
  1. `build: split runtime dependencies into extras`
  2. `build(docker): install only the extras each image needs`
  3. `ci: install all extras in ci jobs`
  4. `docs: document extras and image sizes`
- **Penyesuaian saat implementasi:**
  - Bukan `uv sync --all-extras`: grup `dev` mereferensikan `agent-service[service,ui]`. Dengan
    `--all-extras`, `uv sync` biasa (perintah di AGENTS.md) akan menghapus extras dari `.venv` dan
    merusak hook pre-commit. CI tetap `uv sync --frozen`, jadi commit 3 (`ci:`) tidak dibutuhkan.
    Penggantinya: `test(docker): assert each image ships only its extra`.
  - `pydantic-settings` ada di extra `service` dan `ui`, karena keduanya punya settings sendiri.
  - Streamlit 1.66 bergantung pada `uvicorn`, jadi uvicorn tetap ada di image UI.
  - Ukuran (Docker 29, disk / venv): `service` ±1.000 MB / 551 MB → 505 MB / 187 MB, `ui`
    ±1.000 MB / 551 MB → 881 MB / 458 MB. Sisa besar image UI berasal dari pyarrow dan pandas,
    yang dibawa Streamlit.
- **Acceptance criteria:**
  - [x] Image `service` tidak berisi Streamlit, dan image `ui` tidak berisi langgraph
        (dijaga oleh `test_image_ships_only_its_extra`).
  - [x] Test e2e (`-m integration`) tetap hijau.
- **Squash title:** `build: split dependencies into extras per image (F22)`

### F23: Postgres migration

- **Branch:** `feature/F23-postgres`
- **FR:** FR-32, [ADR 0001](adr/0001-postgres-only.md)
- **File:** `compose.yaml` (service `postgres`, `migrate`, volume), `core/settings.py`
  (`database_url`), `memory/database.py` (engine factory), `memory/migrations/` (Alembic),
  `memory/checkpointer.py`, `memory/thread_metadata.py`, `run_migrate.py`, `tests/conftest.py`
  (fixture Postgres), `.github/workflows/ci.yml` (service Postgres), `docker/Dockerfile`, README
- **Langkah 1 (klarifikasi):** cek versi `langgraph-checkpoint-postgres` yang cocok dengan langgraph
  1.2, dan driver yang diwajibkannya (psycopg 3). Pakai driver yang sama untuk SQLAlchemy supaya
  hanya ada satu driver.
- **Catatan desain:**
  - Image `pgvector/pgvector` (tag di-pin), supaya F43 tidak perlu mengganti image.
  - Service `migrate` menjalankan `alembic upgrade head` dan `setup()` milik saver/store, lalu
    selesai. Service API dan worker memakai
    `depends_on: migrate: condition: service_completed_successfully`.
  - Kontrak publik dipertahankan: `CheckpointerProvider` dan `ThreadMetadataRepository` tetap async
    context manager / repository.
  - `aiosqlite`, `langgraph-checkpoint-sqlite`, dan `SQLITE_DB_PATH` dihapus.
  - Test database memakai database terpisah per sesi test (dibuat dan dihapus oleh fixture). Fixture
    gagal cepat dengan pesan "jalankan `docker compose up -d postgres`".
- **Rencana commit:**
  1. `build(docker): add postgres and migrate services to compose`
  2. `feat(core): add DATABASE_URL setting`
  3. `feat(memory): add async engine and alembic migrations`
  4. `feat(memory): switch checkpointer to postgres`
  5. `feat(memory): move thread metadata to postgres`
  6. `ci: run database tests against a postgres service`
  7. `docs: record F23 postgres decisions`
- **Penyesuaian saat implementasi:**
  - **Commit 2–5 digabung** menjadi `feat(memory): migrate persistence to postgres`.
    `settings.py`, `pyproject.toml`, dan `uv.lock` hanya punya satu isi akhir, jadi commit
    perantara (misalnya setting baru sementara kode masih SQLite) akan gagal di hook pyrefly.
    Commit compose dipindah ke setelah kode siap, supaya stack Docker tidak pernah rusak di tengah.
  - Versi: `langgraph-checkpoint-postgres 3.2.0`, `psycopg 3.3.6` (+ binary, pool 3.3.3),
    `sqlalchemy 2.1.5` (`postgresql+psycopg`, satu driver), `alembic 1.20.0`. Image
    `pgvector/pgvector:0.8.1-pg18` (volume di-mount ke `/var/lib/postgresql`, aturan Postgres 18).
  - Keputusan user: `DATABASE_URL` punya default Postgres compose lokal
    (`postgresql://agent:agent@127.0.0.1:5432/agent_service`).
  - **Windows:** psycopg async tidak bisa memakai `ProactorEventLoop`. Service: uvicorn
    `loop="asyncio:SelectorEventLoop"`. Migrasi: `asyncio.run(..., loop_factory=...)`. Test: hook
    `pytest_asyncio_loop_factories`.
  - **`127.0.0.1`, bukan `localhost`:** di Docker Desktop Windows koneksi ke `::1` menggantung
    sampai timeout (30 detik dengan `connect_timeout=30`, beberapa menit tanpa batas).
  - **`connect_timeout` 5 detik** untuk engine, pool checkpointer, dan migrasi. Default psycopg
    adalah 130 detik, dan di Windows koneksi yang ditolak pun baru terdeteksi setelah timeout.
  - `ThreadMetadataRepository(engine)` tidak lagi berupa context manager. Engine dimiliki
    `DatabaseEngineProvider`. `CheckpointerProvider(database_url)` tetap async context manager,
    tapi tidak lagi memanggil `setup()` (dijalankan migrasi).
  - Lifespan memanggil `ensure_database_migrated` (fail-fast dengan petunjuk `run_migrate`).
  - Test: satu database `agent_service_test_<acak>` per sesi (dibuat, dimigrasi, dihapus),
    `TRUNCATE` semua tabel kecuali tabel migrasi sebelum setiap test, dan `DATABASE_URL` diarahkan
    ke host `.invalid` supaya test tidak menyentuh database dev.
  - Test e2e baru: `migrate` selesai dengan exit code 0 sebelum service start. Port Postgres e2e
    diacak (`POSTGRES_PORT`).
- **Acceptance criteria:**
  - [x] `docker compose up` → `migrate` selesai → service healthy → chat berjalan (e2e, 8 test).
  - [x] Semua test thread (FR-8, FR-9, FR-25, FR-26, FR-28) hijau di Postgres.
  - [x] Tidak ada lagi kode atau dependency SQLite.
- **Squash title:** `feat(memory): migrate persistence to postgres (F23)`

### F24: User auth & CORS

- **Branch:** `feature/F24-user-auth`
- **FR:** FR-33, FR-34
- **File:** `memory/users.py` (`UserRepository`), migrasi tabel `users`, `service/auth.py` (JWT,
  hash password), `service/routes/auth.py`, `service/app.py` (CORS), `schema/requests.py`
  (`user_id` dihapus), `schema/auth.py`, `client/` (login + token), `ui/` (form login di dev
  console), `manage.py` (`create-user`), `core/settings.py`, README, `tests/`
- **Langkah 1 (klarifikasi):** pastikan access token tanpa refresh token cukup untuk demo, dan tentukan
  TTL default.
- **Catatan desain:**
  - JWT HS256 dengan `JWT_SECRET`. Hash password memakai argon2. Klaim `sub` = `user_id`, dan
    `role` = `user` | `service`.
  - **Perubahan kontrak (breaking):** `user_id` tidak lagi diterima dari body/query. Client dan dev
    console diperbarui di PR yang sama. Header `X-User-Id` dihapus.
  - Service account (role `service`) dipakai worker (F41) dan eval (F31).
  - `AUTH_SECRET` dihapus.
- **Rencana commit:**
  1. `feat(memory): add users table and repository`
  2. `feat(service): issue and verify jwt access tokens`
  3. `feat(service): take user id from the access token`
  4. `feat(service): add cors allowlist`
  5. `feat(client): log in and send bearer tokens`
  6. `feat(ui): add login to the streamlit dev console`
  7. `feat: add create-user management command`
  8. `docs: record F24 auth decisions`
- **Langkah 1 (keputusan user):** tanpa refresh token, TTL 12 jam. `JWT_SECRET` wajib (≥ 32 karakter,
  tanpa mode anonim). Login dengan username. Verifikasi token stateless, tanpa query DB per request.
- **Penyesuaian saat implementasi:**
  - **Commit 2–6 digabung** menjadi satu commit `feat(service)`. Menghapus `user_id` dari schema
    langsung mematahkan client dan UI, dan `settings.py`/`app.py` dipakai bersama JWT dan CORS,
    jadi commit perantara akan gagal di hook pyrefly. Hasilnya 5 commit: tabel users, auth + CORS
    (service, client, UI), `create-user`, compose/e2e, docs.
  - Library: `pyjwt 2.15.1` dan `argon2-cffi 25.1.0`, di extra `service`.
  - `Authenticator` (login, terbitkan, verifikasi) dibuat di lifespan. Username yang tidak ada
    diverifikasi terhadap hash tiruan, supaya waktu respons sama dengan password salah.
  - Error auth = `AuthenticationError` → 401 + `WWW-Authenticate: Bearer`, lewat pemetaan error
    domain yang sudah ada. `HTTPBearer(auto_error=False)`, supaya header yang hilang juga 401, bukan
    403.
  - `manage.py` (subcommand `create-user`), bukan file `manage.py` di root, supaya ikut terpasang di
    image (`python -m agent_service.manage`). `--password-stdin` untuk skrip dan e2e.
  - UI: token di `AgentClient` milik session, username di `st.session_state`. Kunci cache daftar
    thread memakai username, karena `st.cache_data` berlaku untuk seluruh proses. Param URL
    `user_id` lama dihapus saat URL ditulis.
  - Fixture test: `client` membawa token `user-a` yang dibuat langsung dari authenticator app (tanpa
    akun di DB), `auth_headers(user)` untuk user lain, dan `anonymous_client`. `JWT_SECRET` test
    diisi fixture autouse.
- **Acceptance criteria:**
  - [x] Tanpa token atau dengan token tidak valid → 401. `/health` tetap tanpa auth.
  - [x] User A tidak bisa membaca, melanjutkan, rename, atau menghapus thread user B (404). Dites di
        route, kontrak client, dan e2e Docker.
  - [x] Preflight CORS dari origin yang diizinkan berhasil, sedangkan origin lain ditolak.
- **Squash title:** `feat(service): add per-user jwt auth and cors (F24)`

### F25: API contract export

- **Branch:** `feature/F25-api-contracts`
- **FR:** FR-35
- **File:** `service/contracts.py` + entrypoint `export_contracts`, `contracts/openapi.json`,
  `contracts/stream-event.schema.json`, `.github/workflows/ci.yml`, CONTRIBUTING (aturan perubahan
  kontrak)
- **Catatan desain:**
  - OpenAPI dari `create_app(...).openapi()` (tanpa lifespan), dan JSON Schema dari
    `STREAM_EVENT_ADAPTER.json_schema()`. Output deterministik (key terurut, newline di akhir).
  - CI menjalankan export lalu `git diff --exit-code contracts/`.
- **Rencana commit:**
  1. `feat(service): export openapi and stream event schemas`
  2. `ci: fail when published contracts are stale`
  3. `docs: document the api contract workflow`
- **Penyesuaian saat implementasi:**
  - CI memakai `export_contracts --check`, bukan `git diff --exit-code contracts/`. `--check`
    juga menangkap file kontrak yang belum ada atau belum di-track (yang tidak terlihat oleh
    `git diff`), dan pesannya menyebut perintah perbaikannya.
  - Ditambah hook pre-commit `api-contracts` dan test `test_published_contracts_match_the_code`,
    supaya lupa ekspor ulang ketahuan saat commit dan saat `pytest`, bukan hanya di CI.
  - `info.version` mengikuti versi package, jadi langkah rilis kini menyertakan ekspor ulang.
  - Doctest `HealthStatus` dan route `/health` bocor ke deskripsi OpenAPI, jadi dipindah ke
    docstring modul. Header `X-Thread-Id` ditambahkan ke respons OpenAPI `/invoke` dan `/stream`.
  - Commit 1 juga memuat dokumentasi header dan pemindahan doctest, karena keduanya mengubah isi
    kontrak yang dipublikasikan.
- **Acceptance criteria:**
  - [x] Mengubah schema tanpa export ulang membuat CI gagal. Diverifikasi dengan menambah field
        ke `ThreadRenameInput` tanpa ekspor: `--check` keluar dengan kode 1 dan test kontrak gagal.
- **Squash title:** `build: publish api contracts for typed clients (F25)`
- **Setelah merge:** rilis **v0.4.0**.

---

## M5: Harness Core → v0.5.0

### F26: Projects

- **Branch:** `feature/F26-projects`
- **FR:** FR-36, FR-30 (override per project), [ADR 0004](adr/0004-project-as-declarative-agent.md)
- **File:** `schema/projects.py`, `memory/projects.py` (`ProjectRepository`), migrasi `projects` +
  `project_id` di metadata thread, `service/routes/projects.py`, `service/run_input.py`,
  `agents/catalog.py` (definisi project built-in), `client/`, `tests/`
- **Langkah 1 (klarifikasi):** bentuk route chat (PRD §11 no. 8) dan isi `ProjectSettings`
  (`max_tokens`, `tool_approval`, dan lainnya).
- **Catatan desain:**
  - Project built-in di-upsert saat startup berdasarkan `id` (idempoten). Mengubah atau menghapusnya
    → 403. Project milik user lain → 404.
  - Di awal setiap run, project dibaca dan diterapkan: model, `max_tokens`, dan instruksi + skill
    yang diteruskan lewat `configurable` (dipakai F27/F28).
  - `ThreadSummary.project_id`, dan listing thread bisa difilter `project_id`.
- **Rencana commit:**
  1. `feat(schema): add project models`
  2. `feat(memory): add projects table and repository`
  3. `feat(service): add project crud routes`
  4. `feat(service): run threads inside a project`
  5. `feat(agents): seed built-in projects`
  6. `feat(client): add project methods`
  7. `docs: record F26 project decisions`
- **Langkah 1 (keputusan user):** route baru `/projects/{project_id}/...` (PRD §11 no. 8). Model:
  request → project → default. Menghapus project ikut menghapus thread-nya. `ProjectSettings`
  hanya `max_tokens`; field lain (mis. `tool_approval`) ditambah fitur yang memakainya.
- **Penyesuaian saat implementasi:**
  - `base_agent_id` tidak bisa diubah (`ProjectUpdate` tanpa field itu, `extra="forbid"` → 422).
    Thread menyimpan `agent_id` di metadata checkpoint.
  - `project_id` disimpan di metadata run hanya untuk thread project, dan ikut dicek
    `is_thread_owner`. Thread project tidak bisa dibuka lewat route agent atau project lain.
  - `RunTarget` (agent, model, `max_tokens`, project) dipakai bersama route agent dan project,
    supaya `invoke`/`stream` hanya punya satu jalur. Cache graph registry menjadi per
    `(agent, model, max_tokens)`.
  - Built-in hanya di-seed jika agent dasarnya terdaftar (`create_app(builtin_projects=...)` untuk
    test), dan diurutkan berdasarkan nama.
  - Commit 1 dan 2 digabung (schema + tabel/repository), dan commit 3–5 digabung (route CRUD, chat
    di project, seed built-in), karena `app.py`, `run_input.py`, dan `threads.py` dipakai bersama.
  - UI Streamlit belum mendapat pemilih project; UI project dibangun di React (F34).
- **Acceptance criteria:**
  - [x] User bisa CRUD project miliknya. Project built-in read-only (403), dan project user lain
        404 di semua endpoint.
  - [x] Run di dalam project memakai model dan `max_tokens` project (dites dengan agent perekam
        dan `ReasoningChatOpenAI`, termasuk prioritas model request).
  - [x] Thread tercatat di project (`ThreadSummary.project_id`) dan bisa difilter
        (`/projects/{project_id}/threads`).
- **Squash title:** `feat(service): add projects as declarative agents (F26)`

### F27: Context builder

- **Branch:** `feature/F27-context-builder`
- **FR:** FR-37, [ADR 0002](adr/0002-own-harness.md)
- **File:** `harness/context.py` (`ContextBuilder`, `PromptSection`), `agents/chatbot.py`,
  `agents/tool_calling.py`, `agents/supervisor.py`, `tests/harness/`
- **Catatan desain:**
  - Bagian berurutan: instruksi agent → instruksi project → indeks skill (F28) → memory (F30) →
    lingkungan (tanggal, timezone dari `clock` yang di-inject). Setiap bagian punya `max_chars`.
  - Agent menerima `ContextBuilder` lewat konstruktor (komposisi). Tanpa project, prompt yang
    dihasilkan sama dengan v1.
  - `harness/` hanya meng-import `core/`, `llm/`, `memory/`, `files/`, `sandbox/`, dan
    `langchain_core`.
- **Rencana commit:**
  1. `feat(harness): add ContextBuilder with ordered prompt sections`
  2. `feat(agents): build system prompts through ContextBuilder`
  3. `feat(agents): include project instructions in prompts`
  4. `docs: record F27 context builder decisions`
- **Langkah 1 (keputusan user):** bagian lingkungan selalu ada di semua agent (FR-37), termasuk
  `chatbot` yang di v1 tanpa system prompt. Acceptance "prompt sama dengan v1" direvisi menjadi
  "isi dan urutan instruksi agent v1 tetap, hanya ditambah bagian lingkungan".
- **Penyesuaian saat implementasi:**
  - Slot skill dan memory berupa `SectionProvider` opsional, supaya F28/F30 hanya menambah provider.
  - `Clock`/`local_now` pindah dari `agents/tool_calling.py` ke `harness/context.py`, karena
    harness tidak boleh meng-import `agents/`. Test layering `tests/harness/test_layering.py`
    menegakkan batas import harness.
  - Expert supervisor memakai `use_project_instructions=False`; instruksi project diterapkan
    supervisor.
  - Commit 2 dan 3 digabung, karena node agent membaca `config` untuk keduanya sekaligus.
  - `interrupt-agent` belum memakai `ContextBuilder` (di luar daftar file F27).
  - Smoke test `qwen3.5:9b`: chatbot tanpa project menjawab tanggal hari ini dengan benar, dan di
    project dengan instruksi "jawab dalam Bahasa Indonesia, satu kalimat" menjawab pertanyaan
    berbahasa Inggris dalam satu kalimat Bahasa Indonesia.
- **Acceptance criteria:**
  - [x] Test snapshot prompt yang dirakit, termasuk batas ukuran per bagian.
  - [x] Instruksi dan urutan prompt agent v1 tetap (test lama hijau setelah disesuaikan untuk
        bagian lingkungan).
- **Squash title:** `feat(harness): assemble prompts per turn with ContextBuilder (F27)`

### F28: Built-in skills

- **Branch:** `feature/F28-built-in-skills`
- **FR:** FR-38, [ADR 0005](adr/0005-skill-format-and-sources.md)
- **File:** `harness/skills/` (`Skill`, `SkillSource`, `FilesystemSkillSource`, `SkillRegistry`,
  parser/validator), `harness/tools/load_skill.py`, `skills/builtin/` (2–3 skill demo),
  `schema/skills.py`, `service/routes/skills.py`, `pyproject.toml` (file `.md` ikut di wheel),
  `tests/`
- **Catatan desain:**
  - Frontmatter diparse dengan `yaml.safe_load`, lalu divalidasi sesuai spesifikasi (nama huruf kecil
    dengan tanda hubung, batas panjang). Skill tidak valid dilewati dengan warning.
  - Registry dibuat sekali di lifespan (`app.state.skill_registry`).
  - `load_skill(name, path=None)` dibuat lewat factory (closure atas registry dan daftar skill
    aktif). Path resource dinormalisasi dan tidak bisa keluar dari folder skill.
  - Model data sudah memuat `scope`, `owner_id`, `version`, dan `read_only`, supaya backlog B1 hanya
    menambah sumber baru.
  - Skill demo: `research-report` (format laporan riset dengan sumber), `meeting-notes`.
- **Rencana commit:**
  1. `feat(harness): parse and validate SKILL.md files`
  2. `feat(harness): add SkillRegistry with a filesystem source`
  3. `feat(harness): add load_skill tool scoped to project skills`
  4. `feat(harness): list active skills in the system prompt`
  5. `feat(service): add read-only skill routes`
  6. `feat(agents): add built-in demo skills`
  7. `docs: record F28 skill decisions`
- **Langkah 1 (keputusan user):** `Project.skill_ids` memakai ID lengkap `<scope>/<name>` (ADR 0005),
  sehingga pola `SkillId` dari F26 diubah (belum dirilis). `load_skill` di-bind hanya pada giliran
  yang project-nya punya skill aktif, termasuk untuk chatbot.
- **Penyesuaian saat implementasi:**
  - Paket di `harness/skills/` (`model`, `parser`, `sources`, `registry`, `toolkit`) dan
    `harness/tools/load_skill.py`. `SkillToolkit` menggabungkan indeks prompt dan tool, dan
    `ContextBuilder.with_skills()` memasangnya, supaya indeks dan tool berasal dari sumber yang sama.
  - `ChatbotAgent` menjadi subclass `ToolCallingAgent` tanpa tool bawaan. `ToolCallingAgent`
    memilih model tanpa/dengan `load_skill` per giliran.
  - `SkillRegistry` dibuat di `create_app` (agent memegang referensinya) dan dimuat di lifespan.
  - `config` di tool disuntikkan LangChain (parameter `RunnableConfig`), tidak terlihat oleh model.
  - Dependency: `pyyaml` dideklarasikan di extra `service` (sebelumnya hanya transitif), dan
    `types-pyyaml` di grup dev untuk pyrefly.
  - Ditambah `AgentClient.list_skills()`/`get_skill()` dan test e2e bahwa skill ada di image service
    (data `.md` ikut di wheel).
  - Commit 1–4 digabung menjadi commit harness, dan 5–6 menjadi commit service/agent, karena
    `app.py`, `catalog.py`, dan `tool_calling.py` disentuh bersama.
- **Acceptance criteria:**
  - [x] `FakeModel` yang di-script memanggil `load_skill` dan menerima isi skill.
  - [x] Skill yang tidak aktif di project → error tool, bukan isi skill.
  - [x] Skill tidak valid dilewati dan tercatat di log, dan startup tetap berjalan.
  - [x] Smoke test `qwen3.5:9b`: transkrip rapat → model memanggil `load_skill("meeting-notes")` dan
        menulis catatan sesuai format skill. Pertanyaan umum ("capital of Japan") → tidak ada skill
        yang dimuat.
- **Squash title:** `feat(harness): add built-in skills with progressive disclosure (F28)`

### F29: Context policy

- **Branch:** `feature/F29-context-policy`
- **FR:** FR-39
- **File:** `harness/context_policy.py` (`ContextPolicy`), state `summary`, `agents/`, `tests/`
- **Catatan desain:**
  - Hitung token dengan `count_tokens_approximately` dan pangkas dengan `trim_messages` dari
    `langchain_core`.
  - Pasangan `AIMessage` dengan `tool_calls` dan `ToolMessage`-nya tidak boleh terpisah.
  - Peringkasan memakai panggilan model bertag `skip_stream`. Ringkasan disimpan di state thread.
- **Rencana commit:**
  1. `feat(harness): trim history to a token budget`
  2. `feat(harness): summarize older turns into thread state`
  3. `feat(agents): apply ContextPolicy before model calls`
  4. `docs: record F29 context policy decisions`
- **Langkah 1 (keputusan user):** `CONTEXT_MAX_TOKENS` default 16.000 (qwen3.5:9b di Ollama
  terukur membaca prompt ±35k token tanpa pemotongan). Peringkasan bertahap: saat anggaran
  terlampaui, giliran lama diringkas sampai riwayat langsung tinggal ±50% anggaran.
- **Penyesuaian saat implementasi:**
  - `trim_messages` tidak dipakai. Pengelompokan unit sendiri (`message_units`) lebih jelas untuk
    menjamin tool call tidak terpisah dan untuk memisahkan bagian yang diringkas.
  - State: `summary` + `summarized_through` (ID message, bukan indeks). Ringkasan masuk
    `ContextBuilder` sebagai bagian `## Summary of earlier conversation` (sebelum lingkungan),
    bukan message tambahan, karena sebagian template chat menolak system message kedua.
  - `SKIP_STREAM_TAG` pindah ke `core/constants.py` (dipakai harness, agent, dan service).
  - Commit 1–2 digabung (satu modul `context_policy.py`), dan commit 3 membawa setting
    `CONTEXT_MAX_TOKENS`.
- **Acceptance criteria:**
  - [x] Thread panjang: input model selalu di bawah `CONTEXT_MAX_TOKENS`.
  - [x] Pasangan tool call tidak pernah terpotong. `/history` tetap lengkap.
  - [x] Smoke test `qwen3.5:9b` (`CONTEXT_MAX_TOKENS=1000`): 8 giliran, satu peringkasan (±15
        detik), dan fakta dari giliran pertama masih dijawab benar lewat ringkasan.
- **Squash title:** `feat(harness): add context trimming and summarization (F29)`

### F30: Long-term memory

- **Branch:** `feature/F30-long-term-memory`
- **FR:** FR-40
- **File:** `memory/store.py` (`StoreProvider`, `AsyncPostgresStore`), `harness/memory.py` (tool +
  bagian prompt), `schema/memories.py`, `service/routes/memories.py`, `tests/`
- **Catatan desain:**
  - Namespace `("users", user_id, "memories")`.
  - `save_memory` memanggil `interrupt()` untuk persetujuan (pola F16) sebelum menyimpan.
  - Pencarian awal memakai teks (tanpa embedding). Index embedding bisa diaktifkan setelah F43.
- **Rencana commit:**
  1. `feat(memory): add postgres store provider`
  2. `feat(harness): add memory tools with user approval`
  3. `feat(harness): inject relevant memories into prompts`
  4. `feat(service): let users list and delete memories`
  5. `docs: record F30 memory decisions`
- **Langkah 1 (keputusan user):** persetujuan lewat balasan teks pada interrupt (tanpa field API
  baru): "yes"/"ya"/... menyimpan, balasan lain menolak dan diteruskan ke model. Prompt berisi
  memory terbaru (maksimal 20, dibatasi 4000 karakter), dan `search_memory` mencari dengan kata
  kunci. Memory untuk `chatbot` dan `research-assistant` saja.
- **Penyesuaian saat implementasi:**
  - Repository di `memory/user_memories.py` (`UserMemoryRepository`, dipakai harness dan route),
    tool di `harness/tools/memory.py`, dan `MemoryToolkit` di `harness/memory.py`. Pool psycopg
    bersama checkpointer dipindah ke `memory/pool.py`.
  - Store diberikan lewat `BaseAgent.build(model, checkpointer, store=None)` dan
    `AgentRegistry(..., store)`, karena pool baru ada di lifespan. Tool dibuat per graph dengan
    closure atas repository, bukan `get_store()` (eksplisit). Slot `memory: SectionProvider` di
    `ContextBuilder` diganti argumen `memories` per panggilan, karena pembacaan store bersifat async.
  - ID memory = uuid5 dari teks. `ToolNode` menjalankan ulang tool call yang sudah disetujui saat
    run dilanjutkan, dan ID deterministik mencegah duplikat (diukur dengan probe).
  - Batas 200 memory dan 500 karakter per memory. Revisi Alembic `0004` (tanpa perubahan skema)
    memaksa database lama menjalankan `run_migrate` sehingga tabel store dibuat.
  - Ditambah `AgentClient.list_memories()`/`delete_memory()` dan test e2e tabel store di image.
  - Commit 2–3 digabung (tool dan bagian prompt berada di toolkit yang sama), dan commit 4 membawa
    perubahan agent, registry, dan client.
- **Acceptance criteria:**
  - [x] Memory tersimpan hanya setelah disetujui, dan muncul di prompt thread lain milik user yang
        sama (test agent dan route).
  - [x] Memory user lain tidak pernah terbaca (NFR-9): repository, prompt, tool, dan route dites.
  - [x] Smoke test `qwen3.5:9b`: "remember my name is Rani, answer in Indonesian" → pertanyaan
        persetujuan → "yes" → tersimpan. Thread baru menjawab "Namamu adalah Rani.", user lain
        tidak tahu namanya, penolakan tidak menyimpan, dan pertanyaan umum tidak memicu
        `save_memory`.
- **Squash title:** `feat(harness): add long-term user memory (F30)`

### F31: Evals & tracing

- **Branch:** `feature/F31-evals-tracing`
- **FR:** FR-41
- **File:** `evals/` (dataset YAML), `src/agent_service/evals/` (runner, scorer, laporan), modul
  tracing (lokasi menurut keputusan Langkah 1), README
- **Langkah 1 (klarifikasi):** backend tracing (PRD §11 no. 7).
- **Catatan desain:**
  - Runner menjalankan kasus lewat `AgentClient` dengan service account, jadi jalurnya sama dengan
    user.
  - Skor deterministik: teks mengandung, tool dipanggil, skill dimuat, dan latensi maksimum. LLM
    judge opsional dengan rubrik.
  - CI hanya menjalankan smoke eval dengan `FakeModel`. Eval dengan LLM asli dijalankan manual,
    dan laporannya tidak di-commit.
- **Rencana commit:**
  1. `feat(evals): add dataset format and runner over AgentClient`
  2. `feat(evals): add deterministic and llm judge scorers`
  3. `feat(service): record run traces`
  4. `docs: document how to run evals`
- **Langkah 1 (keputusan user):** trace di tabel Postgres `run_traces` (tanpa infrastruktur baru),
  dibaca lewat `GET /runs/{run_id}/trace` (pemilik run saja). LLM judge ditunda; F31 hanya memakai
  cek deterministik.
- **Penyesuaian saat implementasi:**
  - Trace: `RunTraceCollector` (`service/tracing.py`, callback LangChain) dipasang per run di
    `/invoke` dan `/stream` (termasuk route project), dan menulis semua span sekali di akhir run.
    Repository di `memory/traces.py`. Isi prompt/jawaban/argumen tool tidak disimpan.
  - Status `interrupted` untuk run yang berhenti bertanya, dan untuk `save_memory` yang memanggil
    `interrupt()` (bukan error).
  - `ModelFactory` memakai `stream_usage=True` supaya token tersedia saat streaming.
  - Eval: `evals/` (dataset, scoring, runner, report, settings) hanya meng-import `client/` dan
    `schema/`; extra `evals`; entrypoint `run_evals`. Skill yang dimuat dibaca dari argumen
    `load_skill` di `/history`, latensi dan token dari trace.
  - Smoke eval CI berjalan sebagai test pytest in-process (`tests/evals/test_datasets.py`), dan
    test e2e menjalankan CLI terhadap stack Compose.
  - Commit 2 (LLM judge) dihapus. Urutan commit: trace dulu (runner membutuhkan endpoint trace).
- **Acceptance criteria:**
  - [x] Eval skill (F28) dengan model asli menghasilkan laporan skor (smoke `qwen3.5:9b`).
  - [x] Trace satu run memuat panggilan model, tool, token, dan latensi.
- **Squash title:** `feat(evals): add evaluation runner and run tracing (F31)`
- **Setelah merge:** rilis **v0.5.0**.

---

## M6: Frontend → v0.6.0

Scope commit frontend: `frontend`. Aturan kode frontend ada di [ADR 0003](adr/0003-frontend-stack.md).

### F32: Frontend scaffold & auth

- **Branch:** `feature/F32-frontend-scaffold`
- **FR:** FR-42, FR-45
- **File:** `frontend/` (Vite, TypeScript strict, Tailwind, shadcn/ui, React Router, TanStack Query,
  ESLint, Vitest), client API hasil generate dari `contracts/`, halaman login, app shell (sidebar
  kosong), `frontend/Dockerfile`, `compose.yaml` (service `web`), `.github/workflows/ci.yml` (job
  frontend), README
- **Langkah 1 (klarifikasi):** package manager (pnpm atau npm), versi Node yang di-pin, dan lokasi
  token di browser.
- **Catatan desain:**
  - Tipe dan client API digenerate (`openapi-typescript` + `openapi-fetch`), tidak ditulis manual.
  - `src/components/ui/` = vendor shadcn, tidak diedit.
  - Image `web` menyajikan hasil build statis.
- **Rencana commit:**
  1. `build(frontend): scaffold vite react typescript app`
  2. `build(frontend): add shadcn ui and app shell layout`
  3. `feat(frontend): generate a typed api client from contracts`
  4. `feat(frontend): add login and authenticated routes`
  5. `build(docker): serve the frontend as a web service`
  6. `ci: lint, type check and test the frontend`
  7. `docs: document frontend commands`
- **Langkah 1 (keputusan user):** pnpm lewat corepack (versi di-pin di `packageManager`), Node 24
  LTS, token di `sessionStorage`, dan API lewat proxy same-origin `/api` (nginx di image `web`,
  proxy Vite di dev), tanpa CORS.
- **Penyesuaian saat implementasi:**
  - Versi diresolusi pnpm dengan `minimumReleaseAge` 14 hari (pnpm 12.17, React 19.3, React
    Router 8.5, Vite 8.3, Vitest 5.1, ESLint 10, Tailwind 4.3, shadcn CLI 4.23). TypeScript dipin
    `~5.9.3`, karena typescript-eslint 8.72 (`<6.1`) dan openapi-typescript 7.13 (`^5`) belum
    mendukung TypeScript 7.
  - shadcn memakai base Radix dan paket `cn` (pengganti clsx + tailwind-merge, milik shadcn).
    Sidebar membawa `sheet`, `tooltip`, `skeleton`, `separator`, dan `src/hooks/use-mobile.ts`.
  - Base URL client = `<origin>/api` absolut, supaya `Request` juga valid di jsdom.
  - Tipe API dicek drift-nya oleh `pnpm check:api` di CI dan hook pre-commit `frontend-check`.
  - Beranda membaca `/info` untuk membuktikan request terautentikasi melewati proxy.
  - Commit 1–4 digabung menjadi satu commit frontend, karena scaffold, vendor, client, dan login
    saling bergantung untuk lolos `tsc` dan ESLint.
- **Acceptance criteria:**
  - [x] `docker compose up` → login → app shell tampil: Vitest (route asli di jsdom, service
        palsu) dan e2e Compose lewat proxy `web` (login, `/info`, SSE). Cek visual di browser
        dilakukan user.
  - [x] Job CI frontend (NFR-11): `check:api`, `tsc`, ESLint, Vitest, build hijau lokal.
- **Squash title:** `build(frontend): scaffold react app with auth and app shell (F32)`

### F33: Chat UI

- **Branch:** `feature/F33-chat-ui`
- **FR:** FR-43, FR-30
- **File:** `frontend/src/features/chat/` (runtime adapter assistant-ui untuk SSE, part reasoning,
  status tool, grup sub-agent, interrupt, peringatan terpotong), `tests`
- **Langkah 1 (klarifikasi):** cek ulang API assistant-ui untuk runtime custom dan part reasoning di
  versi yang di-pin.
  - **Hasil cek (0.15.32, versi terbaru yang lolos jeda 14 hari):** `useExternalStoreRuntime`
    (`messages`, `isRunning`, `onNew`, `onCancel`), part `reasoning`, `tool-call` dengan `result`,
    `parentId` di setiap part, `MessagePrimitive.GroupedParts`, dan status
    `incomplete/length|error|cancelled`. Semuanya cukup tanpa mengubah kontrak API.
  - **Keputusan user:** pemilih **model saja** di composer (agent selalu `default_agent`; agent lain
    lewat Project di F34). Template registry assistant-ui **boleh diedit** (hanya
    `src/components/ui/` yang vendor). URL thread **`/chat/:threadId`**, chat baru di `/`.
- **Catatan desain:**
  - Parser SSE TypeScript memakai tipe dari `stream-event.schema.json`.
  - Perilaku `MessageRenderer` Streamlit menjadi spesifikasi acuan (urutan reasoning → token →
    message, pasangan tool call lewat `tool_call_id`, dan grup per `agent`).
  - Test memakai rekaman SSE asli sebagai fixture.
- **Rencana commit:**
  1. `feat(frontend): stream chat through an assistant-ui runtime adapter`
  2. `feat(frontend): show reasoning and tool call status`
  3. `feat(frontend): render sub-agent steps and interrupts`
  4. `feat(frontend): load thread history`
  5. `docs: record F33 chat ui decisions`
- **Penyesuaian saat implementasi:**
  - Registry assistant-ui saat ini meminta `@assistant-ui/react` ^0.15.36 (dirilis 2026-11-12,
    belum lolos jeda 14 hari). Template (`thread`, `reasoning`, `tool-fallback`, `tool-group`,
    `markdown-text`) diambil langsung dari JSON registry dan lolos type check dengan 0.15.32.
    `elements/` disalin apa adanya; `thread.tsx` dipangkas (tanpa attachment, suara, cabang, edit,
    saran) dan ditambah grup sub-agent, peringatan terpotong, tanda Stop, dan slot pemilih model.
  - Tipe event SSE tidak ada di OpenAPI, jadi digenerate dari `contracts/stream-event.schema.json`
    (`scripts/stream-events.mjs`, json-schema-to-typescript) dan dicek drift-nya di `check:api`.
  - State percakapan di `ChatController` (di luar React, `useSyncExternalStore`), supaya run dan
    riwayat yang terlambat bisa diabaikan saat pindah thread tanpa `setState` di effect.
  - Satu message asisten per pesan user (seperti blok chat Streamlit), dengan status assistant-ui
    untuk terpotong, error, dan dihentikan.
  - Fixture: rekaman SSE dan riwayat asli dari Ollama `qwen3.5:9b` (reasoning, tool call,
    sub-agent, interrupt, terpotong), direkam dengan template smoke di database sementara.
  - Image `web`: cache mount BuildKit untuk store pnpm.
  - Rencana commit 1–4 digabung menjadi satu commit frontend, karena converter yang sama menangani
    token, reasoning, tool, sub-agent, dan riwayat.
- **Acceptance criteria:**
  - [x] Setara Streamlit untuk FR-20, FR-23, FR-24, FR-29, dan FR-30 (dites dengan fixture SSE):
        `conversation.test.ts` (rekaman asli, termasuk riwayat = hasil stream), `chat.test.tsx`
        (route asli di jsdom), dan `chat-controller.test.ts` (model, Stop, pindah thread). Cek
        visual di browser dilakukan user.
- **Squash title:** `feat(frontend): add streaming chat with reasoning and sub-agents (F33)`

### F34: Projects & threads UI

- **Branch:** `feature/F34-projects-ui`
- **FR:** FR-44, FR-36, FR-38
- **File:** `frontend/src/features/projects/`, `frontend/src/features/threads/`, `tests`
- **Catatan desain:** layout ala Claude: sidebar (chat baru, Projects, Recents), halaman Project
  (instruksi, model, pemilih skill dari `GET /skills`, daftar chat). Form memakai komponen form
  shadcn.
- **Rencana commit:**
  1. `feat(frontend): list recents with rename and delete`
  2. `feat(frontend): add projects list and project page`
  3. `feat(frontend): create and edit projects with a skill picker`
  4. `docs: record F34 projects ui decisions`
- **Acceptance criteria:**
  - [ ] User membuat project dengan instruksi + skill, chat di dalamnya, dan thread muncul di project
        tersebut.
  - [ ] Project built-in tampil read-only.
- **Squash title:** `feat(frontend): add projects and thread sidebar (F34)`
- **Setelah merge:** rilis **v0.6.0** (demo showcase).

---

## M7: Files & Execution → v0.7.0

### F35: Artifact storage

- **Branch:** `feature/F35-artifact-storage`
- **FR:** FR-46
- **File:** `files/artifacts.py` (`ArtifactStore`, `LocalArtifactStore`), `memory/artifacts.py`
  (metadata), migrasi, `schema/artifacts.py`, `ChatMessage.artifacts`, `service/converters.py`,
  `service/routes/artifacts.py`, `client/`, `compose.yaml` (volume artifact), `tests/`
- **Catatan desain:**
  - Message menyimpan referensi artifact di `additional_kwargs["artifacts"]` (pola penanda F17),
    lalu converter mengubahnya menjadi `ChatMessage.artifacts`.
  - Download memakai streaming response dengan `Content-Disposition`. Tipe file disimpan saat upload,
    dan nama file disanitasi.
  - `ArtifactStore` berupa protocol, supaya penyimpanan S3-compatible (backlog B7) bisa ditambah.
- **Rencana commit:**
  1. `feat(schema): add artifact references to chat messages`
  2. `feat(files): add local artifact store with metadata in postgres`
  3. `feat(service): add artifact upload and download routes`
  4. `feat(client): upload and download artifacts`
  5. `docs: record F35 artifact decisions`
- **Acceptance criteria:**
  - [ ] Artifact user lain → 404. File lebih besar dari `ARTIFACT_MAX_BYTES` → 413.
- **Squash title:** `feat(files): add artifact storage and download api (F35)`

### F36: Workspace & file tools

- **Branch:** `feature/F36-workspace`
- **FR:** FR-47, FR-48
- **File:** `files/workspace.py` (`Workspace`, `PostgresWorkspace`, `InMemoryWorkspace`),
  `harness/tools/files.py`, `harness/offload.py`, migrasi `workspace_files`, `tests/`
- **Catatan desain:**
  - Path diperlakukan sebagai `PurePosixPath` relatif. `..` dan path absolut ditolak.
  - `edit_file` berupa penggantian string persis (old → new, harus unik).
  - Tool `share_file(path)` menjadikan file workspace sebagai artifact di message jawaban.
  - Output tool yang terlalu besar ditulis ke `tool-outputs/<id>.txt`, dan model menerima cuplikan
    + path.
- **Rencana commit:**
  1. `feat(files): add per-thread workspace with path validation`
  2. `feat(harness): add read, write, edit, list and grep file tools`
  3. `feat(harness): offload large tool outputs to the workspace`
  4. `feat(harness): share workspace files as artifacts`
  5. `docs: record F36 workspace decisions`
- **Acceptance criteria:**
  - [ ] Path traversal ditolak. Workspace thread lain tidak terbaca.
  - [ ] Output tool besar diganti cuplikan + path.
- **Squash title:** `feat(harness): add workspace file tools and output offloading (F36)`

### F37: Sandbox

- **Branch:** `feature/F37-sandbox`
- **FR/NFR:** FR-49, NFR-10
- **File:** `sandbox/` (`Sandbox`, `DockerSandbox`, `FakeSandbox`, `ExecutionResult`),
  `docker/sandbox.Dockerfile` (Python + pandas + numpy + matplotlib, non-root),
  `harness/tools/execute.py` (`run_python`, `run_shell`), `compose.yaml`, `tests/`
- **Langkah 1 (klarifikasi):** cara service menjalankan container. Rekomendasi: service kecil
  `sandbox-runner` yang memegang akses Docker, supaya container API tidak pernah me-mount
  `docker.sock` (akses `docker.sock` setara root di host).
- **Catatan desain:**
  - Container per eksekusi: `network=none`, rootfs read-only + tmpfs `/workspace`, batas memori,
    CPU, dan pids, serta timeout `SANDBOX_TIMEOUT_SECONDS`.
  - File workspace disalin masuk. File baru atau yang berubah disalin keluar ke workspace.
  - Persetujuan sebelum eksekusi mengikuti `ProjectSettings.tool_approval` (interrupt).
  - Dependency berat analisa (pandas, matplotlib) hanya ada di image sandbox, bukan di image service.
- **Rencana commit:**
  1. `feat(sandbox): add Sandbox protocol and fake sandbox`
  2. `build(docker): add sandbox image with data libraries`
  3. `feat(sandbox): run code in hardened docker containers`
  4. `feat(harness): add run_python and run_shell tools`
  5. `feat(harness): ask for approval before execution when the project requires it`
  6. `docs: record F37 sandbox decisions`
- **Acceptance criteria:**
  - [ ] Akses jaringan dari sandbox gagal. Infinite loop berhenti karena timeout.
  - [ ] File yang ditulis di sandbox muncul di workspace.
  - [ ] Test memastikan tidak ada `exec`/`eval`/subprocess untuk kode model di `service/`, `agents/`,
        dan `harness/`.
- **Squash title:** `feat(sandbox): run model code in an isolated docker sandbox (F37)`

### F38: Artifact panel UI

- **Branch:** `feature/F38-artifact-panel`
- **FR:** FR-50
- **File:** `frontend/src/features/artifacts/`, upload di composer, `tests`
- **Catatan desain:** panel kanan memakai komponen shadcn (`Sheet`/`Resizable`, `Table`). PDF
  ditampilkan dengan viewer bawaan browser, tanpa library viewer sendiri.
- **Rencana commit:**
  1. `feat(frontend): show message attachments`
  2. `feat(frontend): preview artifacts in a side panel`
  3. `feat(frontend): upload files from the composer`
  4. `docs: record F38 artifact panel decisions`
- **Acceptance criteria:**
  - [ ] Gambar, CSV, dan PDF dari agent bisa dipreview dan diunduh.
- **Squash title:** `feat(frontend): add artifact panel and file upload (F38)`
- **Setelah merge:** rilis **v0.7.0**.

---

## M8: Data Analytics → v0.8.0

### F39: SQL data source

- **Branch:** `feature/F39-sql-data-source`
- **FR:** FR-51
- **File:** `datasource/` (`SqlDataSource`, `QueryGuard`), `agents/tools/sql.py` (`list_tables`,
  `describe_table`, `run_sql`), seed database demo (`analytics_demo` di service `postgres`), extras
  `analytics` (`sqlglot`), `tests/`
- **Langkah 1 (klarifikasi):** PRD §11 no. 6 (replica, user read-only, masking PII).
- **Catatan desain:**
  - Pertahanan berlapis: user database read-only (utama), `sqlglot` menolak selain satu `SELECT`,
    `LIMIT` dipaksa (`SQL_MAX_ROWS`), dan `statement_timeout` per sesi.
  - Hasil query disimpan ke workspace sebagai CSV, dan model menerima pratinjau tabel + path.
  - Data demo berisi transaksi dengan timestamp, supaya analisa per jendela 2 jam (F42) bisa
    didemokan.
- **Rencana commit:**
  1. `feat(datasource): add read-only sql data source with a query guard`
  2. `feat(agents): add schema introspection and run_sql tools`
  3. `build(docker): seed a demo analytics database`
  4. `docs: record F39 data source decisions`
- **Acceptance criteria:**
  - [ ] `INSERT`, `DROP`, dan multi-statement ditolak. Query lambat berhenti karena timeout.
- **Squash title:** `feat(datasource): add guarded read-only sql tools (F39)`

### F40: Data analyst project

- **Branch:** `feature/F40-data-analyst`
- **FR:** FR-52
- **File:** agent data analyst (instance `ToolCallingAgent` dengan tool SQL, file, dan sandbox),
  `skills/builtin/sql-analysis/`, `skills/builtin/chart-style/`, `skills/builtin/demo-metrics/`
  (semantic layer database demo), seed project "Data Analyst", `evals/data-analyst.yaml`
- **Catatan desain:**
  - Prompt agent dibuat singkat. Prosedur (cara menulis SQL, gaya chart, definisi metrik) ada di
    skill.
  - Chart dibuat di sandbox (matplotlib → PNG), lalu dibagikan sebagai artifact.
  - Tidak ada `exec` di proses service (pelajaran dari referensi
    `langgraph_data_analytics_agents/src/agents/charting_agent.py`).
- **Rencana commit:**
  1. `feat(agents): add data analyst agent with sql, file and sandbox tools`
  2. `feat(agents): add semantic layer skills for the demo database`
  3. `feat(agents): seed the data analyst project`
  4. `test(evals): add a data analyst eval set`
  5. `docs: record F40 data analyst decisions`
- **Acceptance criteria:**
  - [ ] "Penjualan per kategori minggu ini dalam bar chart" → SQL → chart artifact → jawaban.
  - [ ] Skor eval data analyst dengan `qwen3.5:9b` dicatat di memory.md.
- **Squash title:** `feat(agents): add data analyst project (F40)`

### F41: Worker & scheduler

- **Branch:** `feature/F41-worker-scheduler`
- **FR:** FR-53
- **File:** `worker/` (entrypoint `run_worker`, `JobDefinition`, `JobSource`, `WindowCalculator`,
  `JobRunner`), `jobs.yaml`, `memory/job_runs.py` + migrasi, `service/routes/jobs.py`,
  `compose.yaml` (service `worker`), `tests/`
- **Langkah 1 (klarifikasi):** library jadwal: `croniter` + loop sendiri dengan `clock` yang
  di-inject (rekomendasi, mudah dites) atau APScheduler.
- **Catatan desain:**
  - Worker menjalankan agent lewat `AgentClient` dengan service account, sehingga jalur eksekusinya
    sama dengan user.
  - Jendela `[start, end)` dihitung dari waktu jadwal (UTC), bukan `now()`.
  - Constraint unik `(job_id, window_start)` + status run mencegah run dobel, termasuk saat ada
    dua worker. Catch-up dibatasi `MAX_CATCH_UP_WINDOWS`. Run baru tidak dimulai jika run
    sebelumnya masih berjalan.
  - `JobSource` berupa protocol (`YamlJobSource` sekarang), supaya job dari UI (backlog B2) hanya
    menambah sumber.
- **Rencana commit:**
  1. `feat(worker): add job definitions and window calculation`
  2. `feat(memory): add job runs table with unique windows`
  3. `feat(worker): schedule and run jobs through AgentClient`
  4. `feat(service): list jobs and their runs`
  5. `build(docker): add the worker service to compose`
  6. `docs: record F41 worker decisions`
- **Acceptance criteria:**
  - [ ] Test dengan clock palsu: jendela sejajar, catch-up, dan tidak ada duplikat saat dua worker
        berjalan.
  - [ ] Job demo per menit berjalan di compose.
- **Squash title:** `feat(worker): add scheduler for windowed agent jobs (F41)`

### F42: PDF report & scheduled analysis

- **Branch:** `feature/F42-pdf-report`
- **FR:** FR-54
- **File:** `files/pdf.py` (`ReportRenderer`, `AnalysisReport`), agent data analyst (structured
  output laporan), `worker/` (lampiran PDF), `jobs.yaml` (job demo 2 jam), `tests/`
- **Langkah 1 (klarifikasi):** library PDF (PRD §11 no. 9).
- **Catatan desain:**
  - Agent menghasilkan `AnalysisReport` terstruktur (judul, ringkasan, bagian, path tabel dan chart di
    workspace). PDF dirender di kode, bukan oleh LLM.
  - Setiap run job membuat thread baru di project job (judul `<job> <window>`), berisi message
    ringkasan + artifact PDF.
- **Rencana commit:**
  1. `feat(files): render analysis reports to pdf`
  2. `feat(agents): let the data analyst produce a structured report`
  3. `feat(worker): attach pdf reports to scheduled analysis threads`
  4. `docs: record F42 report decisions`
- **Acceptance criteria:**
  - [ ] Job "setiap 2 jam, analisa data jendela 2 jam terakhir" pada database demo menghasilkan thread
        berisi PDF. Isi PDF dicek dengan ekstraksi teks.
- **Squash title:** `feat(worker): deliver scheduled analysis as pdf reports (F42)`
- **Setelah merge:** rilis **v0.8.0**.

---

## M9: Knowledge → v0.9.0

### F43: Knowledge ingestion

- **Branch:** `feature/F43-knowledge-ingestion`
- **FR:** FR-55
- **File:** `knowledge/` (`DocumentParser` per tipe, `Chunker`, `Embedder` +
  `OpenAICompatibleEmbedder` + `FakeEmbedder`, `KnowledgeRepository`), migrasi `documents`,
  `chunks` (pgvector), `ingestion_tasks`, `worker/` (task ingestion), `service/routes/documents.py`,
  extras `rag`, `tests/`
- **Langkah 1 (klarifikasi):** parser (PRD §11 no. 10), model embedding yang tersedia di Ollama, dan
  dimensinya.
- **Catatan desain:**
  - Antrian ingestion di Postgres (`SELECT ... FOR UPDATE SKIP LOCKED`), diproses worker F41.
  - Hash konten mencegah ingestion ulang. Menghapus dokumen juga menghapus chunk-nya.
- **Rencana commit:**
  1. `feat(knowledge): add document parsers and chunker`
  2. `feat(knowledge): add openai-compatible and fake embedders`
  3. `feat(memory): add documents and chunks tables with pgvector`
  4. `feat(worker): process ingestion tasks from a queue`
  5. `feat(service): add project document routes`
  6. `docs: record F43 ingestion decisions`
- **Acceptance criteria:**
  - [ ] Upload PDF → status `ready` → chunk tersimpan dengan embedding. Dokumen rusak → `failed`
        dengan pesan.
- **Squash title:** `feat(knowledge): add document ingestion pipeline (F43)`

### F44: Knowledge retrieval

- **Branch:** `feature/F44-knowledge-retrieval`
- **FR:** FR-56
- **File:** `knowledge/retriever.py`, `agents/tools/knowledge.py` (`search_knowledge`), integrasi
  project (tool aktif jika project punya dokumen), `evals/knowledge.yaml`, `tests/`
- **Catatan desain:** vector search difilter `project_id`, dengan top-k sebagai konstanta. Pencarian
  hybrid (Postgres full-text + vector, digabung dengan RRF) ditambahkan setelah eval menunjukkan
  recall kurang. Jawaban menyertakan sumber.
- **Rencana commit:**
  1. `feat(knowledge): add a project-scoped vector retriever`
  2. `feat(agents): add search_knowledge tool with citations`
  3. `feat(knowledge): combine vector and full-text search`
  4. `test(evals): add a retrieval eval set`
  5. `docs: record F44 retrieval decisions`
- **Acceptance criteria:**
  - [ ] Pertanyaan tentang dokumen dijawab dengan sumber. Dokumen project lain tidak pernah terambil.
- **Squash title:** `feat(knowledge): add project knowledge retrieval (F44)`

### F45: Knowledge UI

- **Branch:** `feature/F45-knowledge-ui`
- **FR:** FR-57
- **File:** `frontend/src/features/knowledge/`, render sumber di jawaban, `tests`
- **Rencana commit:**
  1. `feat(frontend): add a knowledge tab with upload and status`
  2. `feat(frontend): show sources in answers`
  3. `docs: record F45 knowledge ui decisions`
- **Acceptance criteria:**
  - [ ] Upload, pantau status, dan hapus dokumen dari halaman Project.
- **Squash title:** `feat(frontend): add project knowledge tab (F45)`
- **Setelah merge:** rilis **v0.9.0**.

---

## M10: Interop → v0.10.0

### F46: OpenAI-compatible endpoint

- **Branch:** `feature/F46-openai-compatible`
- **FR:** FR-58
- **File:** `schema/openai_compat.py`, `service/routes/openai_compat.py`, `service/converters.py`,
  `tests/` (dengan SDK `openai` sebagai dev dependency)
- **Langkah 1 (klarifikasi):** penamaan model (`project:<id>` / `agent:<id>`), dan apakah thread
  bisa diteruskan lewat header.
- **Catatan desain:** stateless secara default (riwayat dari `messages`). Reasoning dikirim sebagai
  `delta.reasoning_content`. Interrupt dikirim sebagai teks pertanyaan, dan artifact sebagai link.
- **Rencana commit:**
  1. `feat(schema): add openai chat completion models`
  2. `feat(service): add the v1 models endpoint`
  3. `feat(service): add non-streaming chat completions`
  4. `feat(service): stream chat completion chunks`
  5. `test: verify the endpoint with the official openai sdk`
  6. `docs: record F46 interop decisions`
- **Acceptance criteria:**
  - [ ] `AsyncOpenAI` (dengan `httpx.AsyncClient` + `ASGITransport`) bisa chat dan streaming dengan
        sebuah Project.
- **Squash title:** `feat(service): add openai-compatible chat endpoint (F46)`
- **Setelah merge:** rilis **v0.10.0**.

---

## Backlog (belum dijadwalkan)

Fitur yang desainnya sudah disiapkan di fitur lain, tetapi belum masuk milestone. Saat dijadwalkan,
setiap item mendapat ID `Fxx` baru.

| ID | Fitur | Prasyarat | Titik ekstensi yang sudah disiapkan |
|---|---|---|---|
| B1 | Skill lewat UI (buat, edit, hapus) | F28, F34, F35 | `SkillSource` protocol, model `Skill` dengan `scope`/`owner_id`/`version` (ADR 0005) |
| B2 | Job terjadwal lewat UI | F41, F34 | `JobSource` protocol (F41) |
| B3 | Pensiunkan Streamlit dev console | F38 (frontend setara) | Extra `ui` dan target Docker `ui` terpisah (F22) |
| B4 | Adapter protokol AG-UI | F33 | Kontrak SSE native (F25) |
| B5 | Sandbox production (managed atau self-hosted gVisor/Kubernetes) | F37 | `Sandbox` protocol |
| B6 | SSO / OIDC | F24 | Klaim JWT dan `UserRepository` |
| B7 | Artifact storage S3-compatible | F35 | `ArtifactStore` protocol |
