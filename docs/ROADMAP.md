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
| F01 | Core settings | M1 | todo |
| F02 | LLM model factory | M1 | todo |
| F03 | SQLite checkpointer | M1 | todo |
| F04 | API schema | M1 | todo |
| F05 | Agent registry | M1 | todo |
| F06 | Service app | M1 | todo |
| F07 | Invoke & history | M1 | todo |
| F08 | SSE streaming | M1 | todo |
| F09 | User threads | M1 | todo |
| F18 | Thread rename & delete | M1 | todo |
| F10 | Architecture docs | M1 | todo |
| F11 | Agent client | M2 | todo |
| F12 | UI chat | M2 | todo |
| F13 | UI sidebar & threads | M2 | todo |
| F14 | Docker Compose & e2e | M2 | todo |
| F15 | Research assistant | M3 | todo |
| F16 | Interrupt agent | M3 | todo |
| F17 | Supervisor agent | M3 | todo |

## Milestone & Rilis

| Milestone | Fitur | Rilis | Hasil |
|---|---|---|---|
| M0: Bootstrap | F00 | – | Repo, tooling, dan CI siap |
| M1: Core + Service | F01–F10, F18 | `v0.1.0` | API lengkap dengan `chatbot`, dites dengan FakeModel |
| M2: Client + UI | F11–F14 | `v0.2.0` | Chat end-to-end via Docker Compose |
| M3: Agent tambahan | F15–F17 | `v0.3.0` | Tool calling, human-in-the-loop, multi-agent |

## Dependency Graph

```text
F00 ─► F01 ─┬─► F02 ─┐
            └─► F03 ─┴─► F05 ─► F06 ─┬─► F07 ─┬─► F08 ─► F10
F00 ─► F04 ──────────────────────────┘        └─► F16
                                    F06 ─► F09 ─► F18
F04 ─► F11 ─► F12 ─► F13 ─► F14          (F13 juga butuh F18)
F05 ─► F15 ─► F17                        (F17 juga butuh F08, F12)
```

**Urutan eksekusi yang disarankan (satu developer):**
F00 → F01 → F04 → F02 → F03 → F05 → F06 → F07 → F09 → F18 → F08 → F10 → *rilis v0.1.0* → F11 → F12 →
F13 → F14 → *rilis v0.2.0* → F15 → F16 → F17 → *rilis v0.3.0*

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
| FR-26 | F18, F13 | | | |

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
- **File:** `core/settings.py` (`Settings`), `core/constants.py`, `core/logging.py`
  (`LoggingConfigurator`), `tests/core/test_settings.py`
- **Catatan desain:**
  - Tidak ada instance `settings` di level modul. Gunakan `Settings()` di lifespan atau
    `Settings.from_env()`.
  - `AVAILABLE_MODELS` di-parse dari string dipisah koma. Default-nya `[DEFAULT_MODEL]`.
  - Validasi: jika `USE_FAKE_MODEL=false`, maka `LLM_BASE_URL`, `LLM_API_KEY`, dan `DEFAULT_MODEL`
    wajib diisi.
- **Referensi lama:** `core/settings.py` (lihat sisi negatifnya di `:178-251` dan `:262`).
- **Rencana commit:**
  1. `feat(core): add Settings with env validation and model allowlist`
  2. `feat(core): add named constants module`
  3. `feat(core): add LoggingConfigurator with module loggers`
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
  1. `feat(llm): add ModelFactory for openai-compatible models`
  2. `feat(llm): add FakeModel with scripted tool calls`
  3. `test(llm): cover allowlist rejection and model caching`
- **Acceptance criteria:**
  - [ ] Model di luar allowlist menghasilkan `UnknownModelError`.
  - [ ] Tidak ada network call di test.
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
  2. `test(memory): verify checkpoint persistence across provider instances`
- **Acceptance criteria:**
  - [ ] Checkpoint yang ditulis bisa dibaca ulang setelah provider dibuka kembali (`tmp_path`).
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
- **Acceptance criteria:**
  - [ ] `agent_config` yang berisi `thread_id`/`user_id`/`model` ditolak.
  - [ ] Test import memastikan tidak ada dependency di luar pydantic.
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
  2. `feat(agents): add per-agent config schema with strict default`
  3. `feat(agents): add AgentRegistry with not-found and unavailable errors`
  4. `feat(agents): add ChatbotAgent as minimal reference agent`
  5. `test(agents): cover registry lookup, lazy loading and load failure`
  6. `docs(memory-md): record agent registry design decisions`
- **Acceptance criteria:**
  - [ ] Agent yang `load()`-nya gagal tidak menghentikan registry.
  - [ ] Model berbeda menghasilkan graph berbeda (FR-4).
  - [ ] `parse_config` menolak key yang tidak dikenal untuk agent tanpa config custom.
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
  1. `feat(service): add app factory with lifespan wiring`
  2. `feat(service): add optional bearer auth dependency`
  3. `feat(service): map domain errors to http status codes`
  4. `feat(service): add health and info endpoints`
  5. `feat(service): add run_service entrypoint`
- **Acceptance criteria:**
  - [ ] Test dengan `httpx.AsyncClient` + `ASGITransport`.
  - [ ] `AgentNotFoundError` dari route mana pun menjadi 404 berformat `{"detail": ...}` (dites
        lewat route dummy di test).
  - [ ] `/health` lolos tanpa token walaupun `AUTH_SECRET` diset.
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
  2. `feat(service): add RunInputBuilder with interrupt resume support`
  3. `feat(service): validate agent_config against agent config schema`
  4. `feat(service): add invoke endpoint`
  5. `feat(service): add history endpoint`
- **Acceptance criteria:**
  - [ ] Thread yang sedang interrupt menerima `Command(resume=...)` (dites dengan agent fake).
  - [ ] `thread_id` kosong diisi otomatis dan dikembalikan.
  - [ ] `agent_config` yang tidak valid menghasilkan 422 beserta nama field yang salah. Config
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
  1. `feat(service): add SseFormatter for token, message and error frames`
  2. `feat(service): add StreamService handling updates and message chunks`
  3. `feat(service): add stream endpoint`
  4. `test(service): ensure done frame is sent on agent error`
- **Acceptance criteria:**
  - [ ] Urutan frame sesuai PRD §7.3.
  - [ ] Nesting ≤ 2 di semua method.
  - [ ] Ada test untuk error di tengah stream.
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
  2. `feat(service): add threads endpoint with pagination`
  3. `test(service): verify threads are isolated per user`
- **Acceptance criteria:**
  - [ ] User A tidak bisa melihat thread milik user B.
  - [ ] `limit` di luar 1–100 menghasilkan 422.
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
  2. `feat(service): add thread rename endpoint with ownership check`
  3. `feat(service): add thread delete endpoint removing checkpoints`
  4. `feat(service): show custom titles in thread listing`
- **Acceptance criteria:**
  - [ ] Setelah rename, judul baru muncul di `GET /threads`.
  - [ ] Setelah delete, `/history` thread tersebut kosong dan thread hilang dari listing.
  - [ ] User B mendapat 404 saat rename/delete thread milik user A.
- **Squash title:** `feat(service): add thread rename and delete endpoints (F18)`

### F10: Architecture docs

- **Branch:** `feature/F10-docs-architecture`
- **File:** `docs/ARCHITECTURE.md`. Update link di README dan AGENTS.
- **Isi:** alur request (router → `RunInputBuilder` → `AgentRegistry` → graph → checkpointer →
  `StreamService`), diagram layer, siklus hidup lifespan, dan cara menambah agent.
- **Rencana commit:**
  1. `docs: add architecture overview with request flow`
  2. `docs: link architecture doc from readme and agents guide`
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
  1. `feat(client): add SseParser for stream frames`
  2. `feat(client): add sync AgentClient methods`
  3. `feat(client): add async AgentClient methods`
  4. `test(client): cover http errors with mock transport`
- **Acceptance criteria:**
  - [ ] Semua test memakai `httpx.MockTransport` (tanpa server).
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
  1. `feat(ui): add UrlState for thread and agent query params`
  2. `feat(ui): add SidebarView with agent and model pickers`
  3. `feat(ui): list previous threads in sidebar`
  4. `feat(ui): add rename and delete actions for threads`
- **Squash title:** `feat(ui): add sidebar with thread history and pickers (F13)`

### F14: Docker Compose & e2e

- **Branch:** `feature/F14-compose-e2e`
- **File:** `docker/Dockerfile.service`, `docker/Dockerfile.app`, `compose.yaml`,
  `tests/integration/test_compose_e2e.py` (marker `integration`), update README.
- **Catatan desain:** Compose memakai `USE_FAKE_MODEL=true` secara default supaya e2e berjalan
  tanpa API key. Healthcheck memanggil `/health`.
- **Referensi lama:** `docker/Dockerfile.service`, `docker/Dockerfile.app`, `compose.yaml`.
- **Rencana commit:**
  1. `build(docker): add service and app dockerfiles`
  2. `build(docker): add compose with healthcheck and fake model default`
  3. `test(service): add compose end-to-end smoke test`
  4. `docs: document docker compose usage`
- **Acceptance criteria:**
  - [ ] `docker compose up` berjalan, lalu chat di `:8501` mendapat balasan dari FakeModel.
- **Squash title:** `build(docker): add compose stack and e2e smoke test (F14)`
- **Setelah merge:** rilis **v0.2.0**.

---

## M3: Agent Tambahan → v0.3.0

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
- **Acceptance criteria:**
  - [ ] Loop tool calling dites dengan `FakeModel`.
  - [ ] Tool web search di-mock di unit test.
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
