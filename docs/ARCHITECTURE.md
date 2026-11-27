# Arsitektur

Dokumen ini menjelaskan bagaimana service bekerja dari startup sampai satu request selesai, dan
bagaimana menambah agent baru. Aturan menulis kode ada di [AGENTS.md](../AGENTS.md). Requirement dan
kontrak API ada di [PRD.md](../PRD.md).

## Gambaran Besar

Service ini membungkus graph LangGraph dengan API FastAPI. Proses `agent-service` berisi:

- **Registry agent.** Setiap agent dapat membangun graph untuk model mana pun yang diizinkan.
- **Harness** (`harness/`). Prompt dirakit setiap giliran, skill, context policy, long-term memory,
  tool file workspace, dan tool eksekusi kode.
- **Project.** Agent deklaratif: agent kode + instruksi, skill, model, dan pengaturan.
- **Satu database Postgres.** Checkpoint percakapan, akun, project, memory, trace, metadata artifact,
  dan file workspace. Skema lengkapnya ada di [DATA_MODEL.md](DATA_MODEL.md).
- **Data source read-only** (F39). Database analisa terpisah yang dibaca tool data lewat user
  read-only, dipilih per project. Dua dataset demo di-seed compose.
- **Endpoint HTTP.** Login, menjalankan agent (`/invoke`, `/stream`), riwayat, thread, project,
  skill, memory, trace, artifact, dan data source.

Proses lain di stack Compose:

```text
browser ──► web (nginx + React) ──/api──► agent-service ──► postgres (agent_service)
                                              ├──────────► postgres (demo_shop, demo_sensors, read-only)
                                              ├──────────► sandbox-runner ──► Docker (container sekali pakai)
                                              └──────────► LLM OpenAI-compatible
dev console Streamlit (ui) ─────────────────► agent-service
```

Client, UI, dan frontend berkomunikasi dengan service hanya lewat HTTP: Python memakai schema dari
`agent_service.schema`, dan frontend memakai tipe yang digenerate dari `contracts/`.

Dokumen ini menjelaskan arsitektur yang **sudah dibangun** (`v0.7.0` ditambah F47 dan F39). Fitur
berikutnya ada di [ROADMAP](ROADMAP.md), dan keputusan besarnya di [ADR](adr/README.md). Bagian
dokumen ini diperbarui oleh fitur yang mengubahnya.

## Layer

```text
src/agent_service/
├── core/      Settings, konstanta, configure_logging
├── llm/       ModelFactory, ReasoningChatOpenAI, FakeModel
├── agents/    BaseAgent, AgentRegistry, catalog, ChatbotAgent, ToolCallingAgent, InterruptAgent,
│              SupervisorAgent, tools/
├── harness/   ContextBuilder, ContextPolicy, SkillRegistry + SkillToolkit, MemoryToolkit,
│              WorkspaceToolkit, ToolOutputOffloader, tool eksekusi, HarnessContext
├── skills/    Skill built-in (builtin/<name>/SKILL.md), data, bukan kode
├── files/     ArtifactStore (LocalArtifactStore), protocol Workspace (InMemoryWorkspace)
├── sandbox/   Sandbox protocol, RemoteSandbox, DockerSandbox, runner (service sandbox-runner)
├── datasource/ DataSourceRegistry, SqlDataSource, QueryGuard, SchemaInspector, TableProfiler,
│              hasil query ke Parquet (F39)
├── memory/    DatabaseEngineProvider, migrator, CheckpointerProvider, StoreProvider, repository
│              tabel (users, projects, thread_metadata, artifacts, run_traces), PostgresWorkspace,
│              UserMemoryRepository
├── schema/    Model Pydantic untuk API: request, response, event SSE, nama header
├── service/   create_app, lifespan, auth, route, StreamService, ThreadRepository, ProjectService,
│              ArtifactService, RunTraceCollector, contracts
├── evals/     EvalRunner dan scorer (hanya lewat client)
├── client/    AgentClient (sync + async), StreamRun, SseParser
└── ui/        Streamlit dev console: app, LoginView, UrlState, ChatSession, SidebarView, ChatView,
               MessageRenderer
frontend/      React + TypeScript (lihat Frontend)
```

Panah berarti "boleh import". Import ke arah sebaliknya dilarang.

```text
ui ──► client ──► schema
evals ──► client
service ──► agents ──► harness ──► llm, memory, files, sandbox ──► core
agents, service ──► datasource ──► core
service ──► memory ──► core
service ──► schema
frontend ──► contracts/ (tipe hasil generate), lewat HTTP saja
```

- **`schema/` hanya bergantung pada pydantic dan stdlib.** Aturan ini dicek otomatis oleh
  `tests/schema/test_layering.py`. Karena itu konversi objek LangChain ke `ChatMessage` ada di
  `service/converters.py`, bukan di `schema/`.
- **`agents/` tidak mengenal schema API.** `AgentRegistry.list_agents()` mengembalikan `BaseAgent`,
  dan service yang mengubahnya menjadi `AgentInfo`.

## Siklus Hidup

```mermaid
sequenceDiagram
    participant U as uvicorn
    participant A as create_app
    participant L as lifespan
    U->>A: create_app(settings)
    A->>A: buat SkillRegistry, DataSourceRegistry (dari file, belum konek), toolkit, agent
    A->>A: validasi agent default, pasang exception handler, CORS, dan router
    U->>L: startup
    L->>L: SkillRegistry.load() (skill tidak valid dilewati)
    L->>L: DataSourceRegistry.open() (paralel, yang gagal ditandai unavailable)
    L->>L: LocalArtifactStore.prepare(), ModelFactory(settings)
    L->>L: buka engine + CheckpointerProvider + StoreProvider (gagal cepat jika DB mati)
    L->>L: open_sandbox (RemoteSandbox jika SANDBOX_URL diisi)
    L->>L: ensure_database_migrated (gagal jika migrasi belum jalan)
    L->>L: AgentRegistry(model_factory, checkpointer, store).load_all()
    L->>L: ArtifactService, ThreadRepository(cleanups), ProjectService
    L->>L: ProjectService.seed_builtin(BUILTIN_PROJECTS)
    L->>L: simpan ke app.state
    Note over U,L: melayani request
    U->>L: shutdown
    L->>L: tutup pool data source, client sandbox, pool store/checkpointer, dan engine
```

- **Tidak ada side effect saat import.** `create_app()` tanpa argumen membaca `Settings()` saat
  dipanggil. Entrypoint `python -m agent_service.run_service` memanggilnya setelah
  `configure_logging`.
- **`load_all()`** menjalankan `agent.load()` dan meng-compile graph untuk model default. Agent
  yang gagal di tahap ini dicatat di log dan ditandai *unavailable* (503), sementara agent lain
  tetap berjalan.
- **`app.state`** berisi `settings`, `default_agent_id`, `skill_registry`,
  `data_source_registry`, `authenticator`,
  `model_factory`, `registry`, `thread_repository`, `memory_repository`, `trace_repository`,
  `project_service`, dan `artifact_service`. Route mengaksesnya lewat dependency bertipe di
  `service/dependencies.py` (`RegistryDep`, `ThreadRepositoryDep`, dan lainnya), bukan lewat
  `request.app.state` langsung.
- **Agent dibuat sebelum database ada.** Karena itu resource per run (workspace, penerbit artifact,
  sandbox) sampai ke tool lewat runtime context `HarnessContext`, bukan konstruktor (lihat
  [Workspace dan tool file](#workspace-dan-tool-file-f36)).

## Alur Request

Setiap route agent punya dua varian: `/{agent_id}/...` dan `/...` (memakai `DEFAULT_AGENT_ID` =
`chatbot`). Keduanya memanggil helper yang sama. Semua route kecuali `/health` dan `/auth/login`
melewati dependency `current_principal` (lihat [Auth](#auth)), dan `user_id` selalu berasal dari
token.

### `/invoke` dan `/stream`

```mermaid
sequenceDiagram
    participant C as Client
    participant R as Route
    participant G as AgentRegistry
    participant B as build_run_input
    participant X as Graph
    participant S as Checkpointer
    C->>R: POST /{agent_id}/stream
    R->>G: get_agent, get_graph(agent_id, model)
    G-->>R: graph (di-cache per agent + model)
    R->>B: build_run_input(input, principal.user_id, agent, graph)
    B->>B: validasi agent_config, isi thread_id, run_id uuid7
    B->>X: aget_state(thread)
    X->>S: baca checkpoint terakhir
    B->>B: cek pemilik thread, pilih message atau Command(resume)
    B-->>R: RunInput
    R-->>C: 200 + X-Thread-Id (stream dimulai)
    R->>X: StreamService.stream() → astream(...)
    X->>S: tulis checkpoint per langkah
    X-->>C: data: token / message ... data: [DONE]
```

Hal penting dari alur ini:

1. **Validasi selesai sebelum response dimulai.** Agent atau model yang tidak dikenal,
   `agent_config` yang salah, dan thread milik user lain dijawab dengan JSON 404/422. Hanya error
   yang terjadi saat graph berjalan yang menjadi frame `error`, dan stream tetap diakhiri
   `[DONE]`.
2. **Graph per model.** `AgentRegistry.get_graph(agent_id, model)` meminta model ke
   `ModelFactory`, lalu memanggil `agent.build(model, checkpointer)` sekali per pasangan. Model
   pilihan request benar-benar dipakai (FR-4).
3. **Config agent sampai ke node.** `agent_config` yang lolos `config_schema` digabung ke
   `RunnableConfig["configurable"]`.
4. **`/invoke`** memanggil `graph.ainvoke` dan mengembalikan message terakhir, atau pertanyaan
   interrupt, sebagai `ChatMessage` dengan `run_id`.
5. **`/stream`** memakai `StreamService` dengan tiga stream mode:
   - `messages`: menghasilkan frame `reasoning` (jika model mengirim pemikiran) lalu `token`,
     kecuali node bertag `skip_stream`.
   - `updates`: menghasilkan frame `message` untuk jawaban AI, tool call, hasil tool, dan
     interrupt.
   - `custom`: menghasilkan frame `message` dari `get_stream_writer()`.

### Kepemilikan Thread

Thread tidak punya tabel sendiri (lihat [DATA_MODEL.md](DATA_MODEL.md#thread-entitas-virtual)).
Setiap run menyimpan `user_id`, `agent_id`, dan `project_id` (khusus thread project) di
`RunnableConfig["metadata"]` (`thread_access.run_metadata`), dan LangGraph menyalinnya ke
metadata setiap checkpoint. Dari situ:

- **`/invoke` dan `/stream`** boleh melanjutkan thread yang sudah ada hanya jika metadatanya
  cocok. Thread yang belum ada boleh dibuat dengan ID apa pun.
- **`/history`, `PATCH`, dan `DELETE`** mewajibkan thread sudah ada dan cocok.
- **Jika tidak cocok, jawabannya selalu 404, bukan 403,** supaya keberadaan thread tidak bocor.
- **`GET /threads`** (`ThreadRepository.list_threads`) membaca checkpoint pertama setiap thread
  (`step == -1`) dengan filter metadata, mengecek ulang pemiliknya, lalu mengurutkan thread
  berdasarkan checkpoint terakhir.

### Error

| Exception | Status | Asal |
|---|---|---|
| `AuthenticationError` | 401 + `WWW-Authenticate: Bearer` | Login gagal, token tidak ada/rusak/kedaluwarsa |
| `AgentNotFoundError` | 404 | `AgentRegistry.get_agent` |
| `ThreadNotFoundError` | 404 | `ensure_thread_owner` |
| `ProjectNotFoundError` | 404 | `ProjectService` (tidak ada atau milik user lain) |
| `SkillNotFoundError` | 404 | `GET /skills/{id}` |
| `MemoryNotFoundError` | 404 | `DELETE /memories/{id}` |
| `RunTraceNotFoundError` | 404 | `GET /runs/{run_id}/trace` |
| `ArtifactNotFoundError` | 404 | `ArtifactService` (tidak ada, milik user lain, atau ID bukan UUID) |
| `ProjectReadOnlyError` | 403 | Mengubah atau menghapus project built-in |
| `ArtifactThreadConflictError` | 409 | Artifact sudah tertaut ke thread lain |
| `ArtifactTooLargeError` | 413 | File melebihi `ARTIFACT_MAX_BYTES` |
| `InvalidProjectError` | 422 | Agent dasar tidak tersedia, skill tidak dikenal |
| `UnknownModelError` | 422 | `ModelFactory.resolve_name` |
| `RequestValidationError` | 422 (list per field) | Body/query FastAPI, `parse_agent_config` |
| `AgentUnavailableError` | 503 | Agent yang gagal `load()`/`build()` saat startup |
| `ModelNotConfiguredError` | 503 | Model asli tanpa `LLM_BASE_URL`/`LLM_API_KEY` |
| `AgentStepLimitError` | 500, pesan step limit | `/invoke` yang melewati `AGENT_RECURSION_LIMIT` (`GraphRecursionError`). Di `/stream` menjadi frame `error` dengan pesan yang sama |
| Exception lain | 500, `"Internal server error"` | Dicatat dengan `logger.exception` |

Pemetaan ini ada di `service/errors.py` (`DOMAIN_ERROR_STATUS`), dan subclass ikut terpetakan
lewat MRO. Selain handler 500, satu-satunya `except Exception` yang diizinkan ada di
`AgentRegistry._load` (batas plugin agent) dan `StreamService.stream` (batas SSE).

## Auth

Auth per user dengan JWT (FR-33), tanpa mode anonim: `JWT_SECRET` wajib diisi.

- **Akun** ada di tabel `users` (`UserRepository`), dan dibuat hanya lewat CLI
  `python -m agent_service.manage create-user <username> [--role service]`. Username dinormalisasi
  ke huruf kecil (`[a-z0-9._-]`, 3–32 karakter). Password di-hash dengan argon2id.
- **`POST /auth/login`** memanggil `Authenticator.login`. Username yang tidak ada tetap diverifikasi
  terhadap hash tiruan, supaya waktu respons tidak membocorkan username mana yang terdaftar. Kedua
  kegagalan menjawab 401 dengan pesan yang sama.
- **Token** JWT HS256 berisi `sub` (= `user_id`), `role` (`user` atau `service`), `iat`, dan `exp`
  (`JWT_TTL_SECONDS`, default 12 jam). Tidak ada refresh token. Verifikasinya stateless: tanpa query
  database per request, jadi akun yang dihapus tetap bisa memakai tokennya sampai kedaluwarsa.
- **`current_principal`** (`service/dependencies.py`) dipasang per router di `create_app`, dan diminta
  lagi oleh route yang butuh `user_id` (`PrincipalDep`). FastAPI meng-cache dependency per request,
  jadi token diverifikasi sekali. Header yang tidak ada, token rusak, salah tanda tangan,
  kedaluwarsa, atau klaim tidak dikenal menjawab 401 dengan `WWW-Authenticate: Bearer`.
- **Role `service`** disiapkan untuk worker (F41) dan eval (F31). Saat ini aksesnya sama dengan
  `user`.
- **CORS** (FR-34): `CORSMiddleware` hanya mengizinkan origin di `CORS_ORIGINS`, method yang dipakai
  API, header `Authorization`/`Content-Type`, dan mengekspos `X-Thread-Id`. Token dikirim lewat
  header, bukan cookie, jadi `allow_credentials` tidak dipakai.

## System Prompt

`ContextBuilder` (`harness/context.py`, FR-37, [ADR 0002](adr/0002-own-harness.md)) merakit system
prompt di **setiap** panggilan model, dengan urutan bagian yang tetap:

| Urutan | Bagian | Sumber | Batas |
|---|---|---|---|
| 1 | Instruksi agent (tanpa judul) | Konstruktor `ContextBuilder(instructions)` | 8000 |
| 2 | `## Project instructions` | `configurable["project_instructions"]` (F26) | 8000 |
| 3 | `## Skills` | `SkillToolkit` (F28): nama + deskripsi skill aktif | 4000 |
| 4 | `## Memory` | `MemoryToolkit` (F30): 20 memory terbaru milik user | 4000 |
| 5 | `## Summary of earlier conversation` | `ContextPolicy` (F29): ringkasan dari state thread | 4000 |
| 6 | `## Environment` | `clock` yang di-inject: tanggal dan timezone | 300 |

- **Batas per bagian.** Bagian yang melebihi batas dipotong dan diberi penanda `[truncated]`, jadi
  satu sumber yang panjang tidak bisa mendorong bagian lain keluar. Bagian kosong dilewati.
- **Komposisi, bukan base class.** `ChatbotAgent`, `ToolCallingAgent`, dan `SupervisorAgent`
  menerima `ContextBuilder` lewat konstruktor dan memanggil `system_message(config)` di node, yang
  menerima `config` dari LangGraph. Agent tidak lagi memformat `{current_date}` sendiri.
- **Bagian lingkungan selalu ada** (keputusan user, F27), termasuk untuk `chatbot` yang di v1 tidak
  punya system prompt. Prompt v1 hanya bertambah bagian ini; isi dan urutan instruksi agent tetap.
- **Expert supervisor tidak menerima instruksi project** (`use_project_instructions=False`).
  Expert tidak melihat percakapan dan hanya mengerjakan satu tugas teknis. Supervisor, yang
  menyusun jawaban akhir, yang menerapkan instruksi project.
- `interrupt-agent` masih memakai prompt tetap untuk ekstraksi dan jawaban, sehingga instruksi
  project belum berlaku untuknya.

## Context Policy

`ContextPolicy` (`harness/context_policy.py`, FR-39) menjaga riwayat yang dikirim ke model tetap
di bawah `CONTEXT_MAX_TOKENS` (default 16.000). Node model `ToolCallingAgent` dan `SupervisorAgent`
memanggil `prepare()` sebelum setiap panggilan model.

```text
messages (state, lengkap) ──► sesudah summarized_through ──► muat di anggaran? ── ya ──► kirim
                                                                   │ tidak
                                                                   ▼
                              unit lama ──► model (tag skip_stream) ──► summary baru (state)
                              unit terbaru (≤ 50% anggaran) ──► kirim, ringkasan di system prompt
```

- **Unit.** `AIMessage` dengan `tool_calls` selalu satu unit dengan `ToolMessage`-nya, jadi
  pemangkasan tidak pernah memisahkan tool call dari hasilnya. Unit terakhir selalu dikirim.
- **Bertahap** (keputusan user F29). Saat anggaran terlampaui, unit lama diringkas sekaligus sampai
  riwayat langsung tinggal `keep_ratio` (50%) anggaran. Giliran berikutnya tidak meringkas lagi
  sampai anggaran penuh lagi, jadi panggilan model tambahan jarang terjadi.
- **State thread.** `summary` dan `summarized_through` (ID message terakhir yang sudah diringkas)
  disimpan di state graph. `messages` tidak pernah diubah, jadi `/history` tetap lengkap. Thread
  lama tanpa field ini dianggap belum punya ringkasan.
- **Batas.** Anggaran mencakup riwayat dan ringkasan. Ringkasan dibatasi `SUMMARY_MAX_CHARS` atau
  seperempat anggaran. System prompt lain di luar anggaran karena setiap bagiannya sudah dibatasi.
  Unit tunggal yang lebih besar dari anggaran (misalnya hasil tool yang sangat panjang) dipotong di
  salinan yang dikirim, dengan penanda `[truncated]`.
- **Peringkasan.** Model yang sama tanpa tool, bertag `skip_stream` (token dan reasoning-nya tidak
  dialirkan ke chat). Backlog yang lebih besar dari anggaran diringkas per batch. Respons kosong
  mempertahankan ringkasan lama. Kegagalan panggilan model tidak ditangkap, jadi run gagal seperti
  kegagalan model biasa.
- Token dihitung dengan `count_tokens_approximately` (±4 karakter per token). Pada `qwen3.5:9b`
  perkiraan ini 1–8% di atas hitungan Ollama, jadi meleset ke sisi aman.
- Expert supervisor memakai `ContextPolicy()` default (setiap delegasi mulai dari state kosong,
  jadi praktis tidak pernah meringkas). `interrupt-agent` tidak memakainya karena percakapannya
  pendek.

## Long-Term Memory

Memory user (FR-40) disimpan di `AsyncPostgresStore` dengan namespace
`("users", user_id, "memories")`.

```text
model ──► save_memory(memory) ──► interrupt("Save this...?") ──► balasan user (pesan berikutnya)
                                                                   │ "yes"/"ya"/...  │ lainnya
                                                                   ▼                 ▼
                                               UserMemoryRepository.save   ToolMessage "did not approve"
setiap giliran: UserMemoryRepository.list_memories(user, 20) ──► ## Memory di system prompt
```

- **Store per graph.** Pool store baru dibuka di lifespan, sedangkan agent dibuat di `create_app`.
  Karena itu `BaseAgent.build(model, checkpointer, store=None)` menerima store, dan
  `AgentRegistry(model_factory, checkpointer, store)` meneruskannya. `ToolCallingAgent` dengan
  `use_memory=True` membuat `MemoryToolkit(store)` per graph. Tanpa store, graph sama seperti
  sebelum F30.
- **Agent.** `chatbot` dan `research-assistant` (keputusan user F30). Supervisor dan expert-nya
  tidak, karena expert dijalankan tanpa checkpoint sehingga interrupt persetujuan tidak bisa
  dilanjutkan. Tool memory selalu di-bind di agent ber-memory.
- **Persetujuan.** `save_memory` memanggil `interrupt()` dari dalam `ToolNode`. Run berhenti, dan
  pertanyaannya tampil sebagai message AI. Pesan user berikutnya menjadi nilai resume. Jawaban
  dianggap setuju jika diawali kata setuju (`yes`, `ya`, `ok`, `simpan`, ...) dan hanya berisi kata
  setuju/pengisi, jadi "ya tapi ganti jadi X" adalah penolakan yang diteruskan ke model.
- **Idempoten.** Saat run dilanjutkan, `ToolNode` menjalankan ulang semua tool call di giliran
  itu, termasuk `save_memory` yang sudah disetujui. ID memory adalah uuid5 dari teks (tanpa beda
  huruf besar-kecil), jadi penyimpanan ulang menimpa memory yang sama. Dua `save_memory` dalam satu
  giliran ditanyakan bergantian.
- **Isolasi (NFR-9).** User diambil dari `configurable["user_id"]` (diisi service dari token), dan
  prefix namespace store dicocokkan per elemen. `GET`/`DELETE /memories` hanya membaca namespace
  pemilik token. ID memory user lain menjawab 404.
- **Pencarian** tanpa embedding: `search_memory` mengurutkan memory berdasarkan jumlah kata kunci
  (≥ 3 huruf) yang menjadi awal kata di memory, lalu yang terbaru. Karena pencarian berjalan di
  Python, jumlah memory dibatasi 200 per user sampai index embedding tersedia (F43).

## Trace dan Eval

**Trace** (FR-41, keputusan user F31: tabel Postgres, dibaca lewat API).

```text
route /invoke|/stream ──► RunTraceCollector (callback LangChain di config run)
                            on_chat_model_start/on_llm_end   → span model (+ usage_metadata)
                            on_tool_start/on_tool_end/error  → span tool
akhir run ──► save(status) ──► RunTraceRepository.add_spans (satu INSERT) ──► run_traces
GET /runs/{run_id}/trace ──► span milik pemilik token, span `run` lebih dulu
```

- **Span.** `run` (span_id = run_id, durasi seluruh run, total token, status akhir), `model`, dan
  `tool`. Hierarki tidak disimpan; span diurutkan berdasarkan waktu mulai. Panggilan model
  peringkasan (F29) dan expert supervisor ikut tercatat karena callback diwariskan lewat config.
- **Status.** `ok`, `error` (nama exception + pesan, ≤ 500 karakter), atau `interrupted` (run
  berhenti untuk bertanya; `GraphInterrupt` di dalam tool `save_memory` juga dicatat sebagai
  `interrupted`, bukan error).
- **Tanpa konten.** Prompt, jawaban, dan argumen/hasil tool tidak disimpan. Isi percakapan sudah
  ada di checkpoint, jadi trace tidak menggandakan data user.
- **Tulis sekali.** Span dikumpulkan di memori lalu ditulis di akhir run. `SQLAlchemyError` saat
  menulis hanya dicatat di log, jadi database trace yang gagal tidak mengubah jawaban. Stream yang
  diputus client di tengah jalan bisa kehilangan trace-nya.
- **Token** dari `usage_metadata`. `ModelFactory` menyalakan `stream_usage=True`, supaya provider
  OpenAI-compatible mengirim usage di chunk terakhir stream. FakeModel tidak mengirim usage.

**Eval** (`src/agent_service/evals/`, dataset di `evals/`). Package ini hanya meng-import `client/`
dan `schema/` (`tests/evals/test_layering.py`), dan punya extra `evals` sendiri (pydantic-settings,
pyyaml).

- `EvalRunner` menjalankan setiap kasus di thread baru lewat `AgentClient` (service account):
  `ainvoke` → `aget_history` (tool call, skill yang dimuat lewat argumen `load_skill`) →
  `aget_run_trace` (latensi di service dan token). Error HTTP menggagalkan kasus itu saja.
- Skor deterministik di `scoring.py`. LLM judge ditunda (keputusan user F31).
- `run_evals` menulis `eval-reports/eval-<waktu>.json` dan `.md`, exit code 0/1/2 (lolos, ada kasus
  gagal, konfigurasi atau dataset salah).
- CI: `tests/evals/test_datasets.py` memvalidasi semua dataset dan menjalankan `evals/smoke.yaml`
  dengan FakeModel in-process. Test e2e menjalankan CLI `run_evals` terhadap stack Compose.

## Skill

Skill built-in (FR-38, [ADR 0005](adr/0005-skill-format-and-sources.md)) memakai format Agent
Skills: `skills/builtin/<name>/SKILL.md` (frontmatter YAML + Markdown) dan file pendukung di
subfolder.

- **Pemuatan.** `SkillRegistry([FilesystemSkillSource(BUILTIN_SKILLS_DIR)])` dibuat di `create_app`
  (agent butuh referensinya), lalu `load()` dijalankan di awal lifespan. `parse_skill_markdown`
  memvalidasi `name` (sama dengan nama folder, huruf kecil, ≤ 64), `description` (≤ 1024),
  `compatibility`, dan `metadata`. Skill tidak valid dicatat lalu dilewati, tanpa menggagalkan
  startup. Sumber lain (B1) cukup memenuhi protokol `SkillSource`.
- **ID** berbentuk `<scope>/<name>` (`builtin/meeting-notes`), dipakai di `Project.skill_ids`.
  Model memakai nama pendek, karena nama unik di antara skill aktif satu project.
- **Progressive disclosure.** `SkillToolkit` mengisi slot `skills` di `ContextBuilder` dengan nama
  dan deskripsi skill aktif (dari `configurable["project_skill_ids"]`), dan menyediakan tool
  `load_skill(name, path?)`. Tool membaca config yang disuntikkan LangChain (tidak terlihat di
  schema tool), menolak skill yang tidak aktif dengan `ToolException`, hanya membaca file yang
  tercatat sebagai resource skill, dan memotong isi di 20.000 karakter.
- **Bind per giliran.** `ToolCallingAgent` (termasuk `ChatbotAgent`, yang kini dibangun di atasnya
  tanpa tool bawaan) menyiapkan dua model: tanpa tool skill, dan dengan `load_skill`. Model kedua
  hanya dipakai pada giliran yang project-nya punya skill aktif. Tanpa tool sama sekali, graph
  chatbot tetap `agent → END`.
- **Validasi project.** `ProjectService` menolak `skill_ids` yang tidak dikenal registry (422), dan
  saat seeding melewati skill built-in yang tidak termuat.
- Supervisor belum memakai skill.

## Project

Project adalah agent deklaratif (FR-36, [ADR 0004](adr/0004-project-as-declarative-agent.md)):
satu agent kode plus konfigurasi.

- **Penyimpanan.** Tabel `projects` (`ProjectRepository`), dengan `skill_ids` dan `settings` sebagai
  JSONB. `scope = builtin` berarti `owner_id` kosong (dijaga check constraint).
- **Akses** ada di `ProjectService` (`service/projects.py`). Project milik user lain → 404,
  mengubah atau menghapus built-in → 403, dan agent yang tidak tersedia → 422. Menghapus project
  menghapus semua thread di dalamnya lebih dulu (`ThreadRepository.delete_project_threads`).
- **`base_agent_id` tidak bisa diubah**, karena thread menyimpan `agent_id` di metadata checkpoint.
  Mengganti agent akan membuat thread lama tidak bisa dibuka, atau dijalankan dengan graph yang
  tidak cocok dengan state-nya.
- **Built-in** didefinisikan sebagai data (`BUILTIN_PROJECTS` di `agents/catalog.py`) dan di-upsert
  di lifespan, hanya jika agent dasarnya terdaftar. Urutannya di daftar berdasarkan nama.
- **Run di project.** Route `/projects/{project_id}/...` membaca project di awal setiap run, lalu
  membentuk `RunTarget`: agent dasar, model (request → project → default), `max_tokens` project,
  dan `ProjectRunContext`. `AgentRegistry.get_graph(agent, model, max_tokens)` meng-cache graph per
  ketiganya. Instruksi, skill, dan data source project diteruskan lewat `configurable`
  (`project_id`, `project_instructions`, `project_skill_ids`, `project_tool_approval`,
  `project_data_source_ids`, kuncinya di `core/constants.py`).
- **Isolasi thread.** `run_metadata` menulis `project_id` untuk thread project, dan
  `is_thread_owner` membandingkannya. Thread project tidak bisa dibuka lewat route agent atau
  project lain, dan sebaliknya. Thread tanpa key `project_id` (termasuk thread sebelum F26) adalah
  thread tanpa project. Listing route agent menyaring thread project di Python, karena key yang
  tidak ada tidak bisa difilter dengan containment JSONB.

## Kontrak API

`service/contracts.py` membuat dua file di `contracts/` (FR-35):

- **`openapi.json`** dari `create_app(...).openapi()` dengan `Settings` tiruan (tanpa `.env`, tanpa
  lifespan, jadi tanpa database atau LLM) dan hanya `ChatbotAgent`. Route agent memakai path
  generik `/{agent_id}/...`, jadi daftar agent tidak memengaruhi kontrak. `info.version` diambil
  dari versi package. Header `X-Thread-Id` didokumentasikan di respons `/invoke` dan `/stream`
  (`RUN_RESPONSE_HEADERS`), dan route terlindungi mendeklarasikan skema `HTTPBearer`.
- **`stream-event.schema.json`** dari `STREAM_EVENT_ADAPTER.json_schema()`, ditambah `$schema`
  (draft 2020-12), judul `StreamEvent`, dan penjelasan penanda akhir `[DONE]` yang bukan JSON.

Serialisasinya deterministik: key terurut, indentasi 2, UTF-8, LF, dan newline di akhir.
`python -m agent_service.export_contracts` menulis file. Opsi `--check` hanya membandingkan dan
keluar dengan kode 1 jika ada file yang usang atau hilang (dipakai CI dan hook pre-commit
`api-contracts`).

Docstring model dan route menjadi deskripsi di OpenAPI, jadi doctest-nya ditaruh di docstring
modul. Test `test_contracts_carry_no_internal_docstrings` menjaga aturan ini.

## Frontend

React + TypeScript di `frontend/` (FR-42, [ADR 0003](adr/0003-frontend-stack.md)).

```text
browser ──► web :3000 (nginx) ── /            → dist/ (SPA, fallback index.html)
                               └─ /api/*      → agent-service:8080/* (proxy, SSE tanpa buffering)
dev:  vite :5173 ── /api/* → AGENT_URL (default 127.0.0.1:8080)
```

- **Same-origin** (keputusan user F32): frontend selalu memanggil `<origin>/api`. Tanpa CORS, dan
  URL service tidak di-bake ke build. `API_UPSTREAM` image `web` diisi lewat template envsubst
  nginx.
- **Auth.** `SessionStore` menyimpan token di `sessionStorage` beserta `expiresAt` absolut. Sesi
  yang kedaluwarsa dibuang saat dibaca. `AuthProvider` memasang client `openapi-fetch` yang
  membaca token dari store di setiap request, dan logout saat respons 401 untuk request yang
  membawa token. `RequireAuth` mengarahkan ke `/login`.
- **Route** (mode data React Router): `/login`, lalu layout terproteksi `AppShell` (sidebar
  shadcn: chat baru, Recents, user + logout) dengan `ChatPage` di `/` (chat baru) dan
  `/chat/:threadId` (keputusan user F33). Kedua route memakai komponen yang sama, jadi state tetap
  utuh saat URL chat baru diganti ke thread yang baru dibuat.
- **Tipe** dari `contracts/openapi.json` (`openapi-typescript`) dan
  `contracts/stream-event.schema.json` (`scripts/stream-events.mjs`, json-schema-to-typescript),
  dicek drift-nya oleh hook `frontend-check` dan CI.

### Chat (F33)

```text
ChatPage ── useChatRuntime ── useExternalStoreRuntime (assistant-ui) ──► Thread
                │
                └─ ChatController (state di luar React, useSyncExternalStore)
                      ├─ ChatService.startRun  → POST /stream (parseAs stream) → readStreamEvents
                      ├─ ChatService.loadHistory → POST /history
                      └─ conversation.ts: applyStreamEvent → toThreadMessages
```

- **Spesifikasi acuan** adalah `MessageRenderer` Streamlit. Semua message setelah satu pesan user
  menjadi satu message asisten: reasoning dan token live, lalu diganti message utuh. Hasil tool
  mengisi part tool call yang `tool_call_id`-nya sama. Part dari message ber-`agent` membawa
  `parentId` = nama expert, dan `thread.tsx` mengelompokkannya per expert (FR-23).
- **Status message** memakai status assistant-ui: `incomplete/length` untuk `truncated` (FR-30),
  `incomplete/error` untuk frame `error`, dan `incomplete/cancelled` saat user menekan Stop. Teks
  yang sudah di-stream tetap tampil saat run dihentikan.
- **Pindah thread** menaikkan `generation` controller dan membatalkan run aktif (`AbortController`),
  sehingga event atau riwayat yang terlambat dari thread sebelumnya diabaikan.
- **Agent** selalu `default_agent` lewat `POST /stream` untuk chat umum. Model dipilih di composer
  dari `/info` (keputusan user F33). Agent lain dipakai lewat Project (F34).
- **Template.** `src/components/assistant-ui/elements/` disalin dari registry assistant-ui tanpa
  diubah; ESLint mematikan aturan yang dilanggar upstream hanya di folder itu. `thread.tsx`
  dipangkas dan disesuaikan (keputusan user: template boleh diedit). Registry saat ini meminta
  `@assistant-ui/react` ^0.15.36 (belum lolos jeda 14 hari); template lolos type check dengan
  0.15.32 yang di-pin.
- **Test** memakai rekaman SSE dan riwayat asli (`src/features/chat/__fixtures__/`, Ollama
  `qwen3.5:9b`). Riwayat thread yang dibuka ulang harus menghasilkan message yang sama persis
  dengan hasil stream-nya.
- **Vendor.** `src/components/ui/` dan `src/hooks/use-mobile.ts` hasil CLI shadcn tidak diedit.
  ESLint mematikan tiga aturan untuk file vendor (Fast Refresh, `react-hooks/purity`,
  `react-hooks/set-state-in-effect`); kode aplikasi tetap memakai semuanya.
- **Tooling.** Node 24, pnpm 12 via corepack, `minimumReleaseAge` 14 hari (setara
  `exclude-newer` uv). TypeScript dipin `~5.9`, karena typescript-eslint dan openapi-typescript
  belum mendukung TypeScript 7.

### Projects dan threads (F34)

```text
AppShell ── RecentsList ── useThreads(null) ── ThreadsService → GET/PATCH/DELETE /threads
/projects ─────────────── ProjectsPage ── useProjects → GET /projects
/projects/new, /:id/edit ─ ProjectForm (react-hook-form + zod) → POST/PATCH /projects, GET /skills
/projects/:id[/chat/:t] ── ProjectChatPage ── ChatPage key=projectId, projectId
                              ├─ ChatService(api, projectId) → /projects/{id}/stream, /history
                              └─ ProjectOverview (welcome) ── useThreads(projectId)
```

- **Scope thread.** Chat umum dan chat project memakai komponen yang sama dengan `projectId`
  `null` atau id project. URL dan query key (`["threads", projectId ?? "general"]`) ada di
  `features/threads/thread-paths.ts`. Recents hanya berisi chat umum, karena `GET /threads` hanya
  mengembalikan thread tanpa project (keputusan user F34).
- **Refresh daftar thread.** `ChatController` memanggil `onThreadCreated` dan `onRunFinished`;
  `ChatPage` meng-invalidate query thread scope-nya, sehingga judul dan urutan di sidebar atau
  halaman project ikut berubah. Rename dan hapus meng-invalidate lewat mutation.
- **Halaman project** adalah `ChatPage` dengan `welcome` = ringkasan project, jadi composer ada di
  halaman project (keputusan user F34). `key={projectId}` membuat controller baru saat pindah
  project; URL chat baru → thread tetap memakai komponen yang sama.
- **Read-only.** Project built-in (`read_only`) tidak punya menu edit/hapus, dan halaman edit-nya
  hanya menampilkan pemberitahuan. Service tetap menjadi penjaga (403).
- **Form** memvalidasi batas yang sama dengan `schema/projects.py` (nama 1–80, deskripsi ≤ 500,
  instruksi ≤ 8000, maksimal 20 skill, batas token ≥ 1). Error service (misalnya model tidak
  dikenal) tampil di bawah form.

### Artifact panel (F38)

```text
ChatPage ── ArtifactWorkspace (ArtifactPanelContext, ResizablePanelGroup | Sheet)
             ├─ Thread
             │   ├─ ComposerAttachments / ComposerAddAttachment ── ArtifactAttachmentAdapter
             │   │      add(): POST /artifacts saat dipilih · remove(): DELETE · kirim: artifact_ids
             │   ├─ UserMessage: metadata.custom.artifacts ──┐
             │   └─ AssistantMessage: data part "artifacts" ─┴─ ArtifactCards → panel.open()
             │       MarkdownText img → ArtifactMarkdownImage (nama file = artifact gambar?)
             └─ ArtifactPanel → ArtifactPreview (useArtifactContent: GET /artifacts/{id} → Blob)
                  image <img> · csv papaparse → Table · pdf <iframe> · teks <pre> · unduh
```

- **Token, bukan cookie.** Unduhan service membutuhkan header `Authorization`, jadi isi file
  dibaca lewat client bertipe menjadi `Blob`, lalu ditampilkan dan diunduh lewat object URL.
  Header `Content-Disposition: attachment` dan CSP `sandbox` dari service tetap melindungi akses
  langsung ke URL API.
- **Gambar markdown.** Path relatif yang namanya sama dengan artifact gambar di jawaban yang sama
  ditampilkan dari artifact itu; path relatif lain hanya menampilkan teks alt, karena path
  workspace tidak bisa dimuat browser. URL absolut dirender seperti biasa.
- **Upload saat dipilih.** `ArtifactAttachmentAdapter.add` adalah async generator yang melapor
  status uploading → siap atau error, sehingga 413 terlihat di chip sebelum pesan dikirim.

## Persistence

Satu database Postgres di `DATABASE_URL` ([ADR 0001](adr/0001-postgres-only.md)). ERD, kamus
kolom, kardinalitas, dan alur penghapusan ada di [DATA_MODEL.md](DATA_MODEL.md).

| Tabel | Pemilik | Isi |
|---|---|---|
| `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations` | `AsyncPostgresSaver` (via `CheckpointerProvider`) | State graph per langkah, termasuk metadata `user_id`/`agent_id`/`project_id` |
| `thread_metadata` | `ThreadMetadataRepository` (SQLAlchemy Core) | Judul custom hasil rename |
| `users` | `UserRepository` (SQLAlchemy Core) | Akun login: username, hash argon2, role |
| `projects` | `ProjectRepository` (SQLAlchemy Core) | Project built-in dan milik user |
| `store`, `store_migrations` | `AsyncPostgresStore` (via `StoreProvider`) | Long-term memory user (F30) |
| `run_traces` | `RunTraceRepository` (SQLAlchemy Core) | Trace run: satu baris per span run/model/tool (F31) |
| `workspace_files` | `PostgresWorkspace` (SQLAlchemy Core) | File workspace per thread: path, isi (bytes), ukuran (F36) |
| `artifacts` | `ArtifactRepository` (SQLAlchemy Core) | Metadata artifact: pemilik, thread, nama, tipe, ukuran (F35). Isi file di `ArtifactStore` |
| `alembic_version` | Alembic | Revisi skema tabel aplikasi |

- **Satu driver.** Checkpointer dan SQLAlchemy sama-sama memakai psycopg 3. `DATABASE_URL` ditulis
  `postgresql://...`, dan `sqlalchemy_url()` menambahkan `+psycopg` untuk SQLAlchemy.
- **Tiga pool per proses.** `CheckpointerProvider` dan `StoreProvider` masing-masing membuka
  `AsyncConnectionPool` psycopg lewat `memory/pool.py` (autocommit, tanpa prepared statement, baris
  dict, sesuai syarat saver/store LangGraph). `DatabaseEngineProvider` membuka engine SQLAlchemy.
  Semuanya mengecek koneksi saat startup dengan `connect_timeout` 5 detik, karena default psycopg
  adalah 130 detik.
- **Migrasi terpisah dari service.** `python -m agent_service.run_migrate` (service compose
  `migrate`) menjalankan `AsyncPostgresSaver.setup()`, `AsyncPostgresStore.setup()`, lalu
  `alembic upgrade head`. Revisi `0004` tidak mengubah skema; ia memaksa database lama dimigrasi
  ulang supaya tabel store pasti ada. Lifespan hanya memanggil `ensure_database_migrated`, yang membandingkan `alembic_version` dengan revisi terbaru.
  Tabel aplikasi baru ditambahkan di `memory/tables.py` beserta revisi di `memory/migrations/`.
- **Event loop.** psycopg async tidak bisa memakai `ProactorEventLoop`, loop default di Windows.
  `run_service` memberi uvicorn `loop="asyncio:SelectorEventLoop"`, `run_migrate` memakai
  `asyncio.run(..., loop_factory=asyncio.SelectorEventLoop)`, dan test memakai hook
  `pytest_asyncio_loop_factories`.

Penghapusan thread memanggil `adelete_thread`, menghapus judulnya, lalu menjalankan setiap
`ThreadDataCleanup` (artifact thread F35, workspace thread F36). Tidak ada foreign key, jadi
penghapusan berantai ini dilakukan aplikasi. `run_traces` sengaja tidak ikut terhapus (lihat
[DATA_MODEL.md](DATA_MODEL.md#data-yang-tidak-ikut-terhapus)).

### Artifact (F35)

```text
POST /artifacts ── ArtifactService.upload ── LocalArtifactStore.write (.part → rename)
                                         └─ ArtifactRepository.add (metadata, thread_id kosong)
POST /invoke|/stream {artifact_ids} ── build_attached_run_input
    ├─ ArtifactService.resolve_attachments  (milik user? 404; thread lain? 409)
    ├─ build_run_input → HumanMessage(additional_kwargs["artifacts"] = [ArtifactRef])
    └─ ArtifactService.link(thread_id)      (setelah kepemilikan thread lolos)
GET /history ── langchain_to_chat_message → ChatMessage.artifacts
DELETE thread/project ── ThreadRepository._remove → ArtifactService.delete_thread_data
```

- **Isi dan metadata terpisah.** `files/artifacts.py` berisi protocol `ArtifactStore` dan
  `LocalArtifactStore` (folder `ARTIFACT_DIR`, volume `artifacts` di compose). Metadata ada di
  tabel `artifacts`. Store S3-compatible (backlog B7) cukup mengimplementasikan protocol.
- **Batas ukuran** ditegakkan saat isi upload disalin ke store; file `.part` dihapus jika melebihi
  `ARTIFACT_MAX_BYTES` (413). Proxy nginx image `web` punya batas sendiri (`API_MAX_BODY_SIZE`).
- **Keamanan unduhan.** Selalu `Content-Disposition: attachment` (nama ASCII + `filename*` UTF-8),
  `X-Content-Type-Options: nosniff`, dan `Content-Security-Policy: sandbox`, jadi HTML/SVG tidak
  pernah dirender di origin aplikasi. Nama file disanitasi (tanpa path dan karakter kontrol).
- **Satu artifact, satu thread.** Artifact ditautkan ke thread saat pertama kali dikirim, supaya
  penghapusan thread tahu file mana yang ikut dihapus. Lampiran tidak bisa menjadi jawaban
  interrupt (422), karena `Command(resume=...)` tidak membawa message human.
- **Isolasi.** Semua pembacaan disaring `owner_id`; artifact user lain dan ID yang bukan UUID
  dijawab 404 dengan pesan yang sama.

### Workspace dan tool file (F36)

```text
service: build_attached_run_input
    ├─ lampiran → ArtifactService.copy_to_workspace → uploads/<nama>
    │            HumanMessage.additional_kwargs["workspace_files"]
    └─ RunInput.context = HarnessContext(workspace, artifacts=ArtifactService)
graph.ainvoke / astream (..., context=run.context)
ToolCallingAgent(files=WorkspaceToolkit)
    ├─ call_model: with_attachment_notes(messages) → model melihat path lampiran
    └─ ToolNode(awrap_tool_call=ToolFailureGuard.around(ToolOutputOffloader))
          read_file · write_file · edit_file · list_files · grep · share_file
          ToolRuntime[HarnessContext] → workspace + thread_id/user_id dari config
          output > TOOL_OUTPUT_MAX_TOKENS → tool-outputs/<id>.txt + cuplikan
```

- **Runtime context, bukan konstruktor.** Agent dibuat di `create_app` sebelum database ada, jadi
  workspace dan penerbit artifact datang per run lewat `context=` (`harness/runtime.py`). Run tanpa
  context (sub-agent, test unit) membuat tool file menjawab "workspace not available".
- **Isolasi.** Tool tidak menerima thread dari model: `thread_id` dan `user_id` dibaca dari config
  yang ditetapkan service setelah kepemilikan thread diperiksa. Path dinormalisasi
  (`normalize_workspace_path`): path absolut, huruf drive, `..`, dan karakter kontrol ditolak.
- **Isi bytes.** File biner (lampiran PDF, gambar dari sandbox F37) disimpan apa adanya; `read_file`
  dan `grep` hanya membaca teks UTF-8. `share_file` menerbitkan file apa pun sebagai artifact yang
  tertaut ke thread, lewat `ToolMessage.additional_kwargs["artifacts"]`.
- **Offload.** `ToolOutputOffloader` memotong output tool lain yang melebihi
  `TOOL_OUTPUT_MAX_TOKENS`, menyimpan isi utuh di `tool-outputs/<tool_call_id>.txt`, dan memberi
  model seperempat batas sebagai cuplikan. `read_file`, `list_files`, dan `grep` membatasi
  outputnya sendiri (paging per baris), jadi tidak di-offload.
- **`grep` literal.** Pola dari model dicocokkan sebagai substring, bukan regex, karena `re` tidak
  punya timeout dan berjalan di event loop service.

### Sandbox (F37)

```text
agent-service                                   sandbox-runner (satu-satunya dengan docker.sock)
 run_python / run_shell                          POST /execute  (Bearer SANDBOX_TOKEN)
  ├─ tool_approval = "always"? → interrupt         └─ DockerSandbox → Docker Engine API (httpx UDS)
  ├─ workspace thread → ExecutionRequest.files         create (network none, rootfs ro, uid 10001,
  └─ RemoteSandbox ──── HTTP internal compose ───►       no caps, 512 MB, 1 CPU, 128 pids)
       ExecutionResult.files → workspace ◄────────     put archive /workspace (volume anonim)
                                                       start → wait (timeout → kill)
                                                       logs → archive /workspace → delete -v
```

- **NFR-10.** Kode model tidak pernah dijalankan di proses service. `tests/test_no_code_execution.py`
  memeriksa AST `service/`, `agents/`, `harness/`, dan `sandbox/`: tanpa `exec`/`eval`/`compile`,
  `subprocess`, `os.system`/`exec*`/`spawn*`, atau `asyncio.create_subprocess_*`.
- **Akses Docker terpisah.** `docker.sock` setara root di host, jadi hanya `sandbox-runner` (tanpa
  port di host) yang me-mount-nya. Agent-service memanggilnya lewat `RemoteSandbox` dengan token
  bersama; tanpa `SANDBOX_URL`, tool eksekusi tidak di-bind.
- **Satu container per eksekusi.** `/workspace` berupa volume anonim karena arsip tidak bisa disalin
  ke tmpfs container yang belum berjalan; image sandbox membuat folder itu milik UID 10001. Kode
  ditulis ke `/workspace/.sandbox/` (tidak disalin keluar). Hanya file yang baru atau berubah yang
  kembali, dibatasi 50 MB; stdout/stderr dipotong 64 KB. Symlink dan path di luar `/workspace`
  diabaikan saat arsip dibuka.
- **Persetujuan.** `ProjectSettings.tool_approval` diteruskan ke `configurable`. Dengan `always`,
  tool memanggil `interrupt()` berisi kodenya sebelum eksekusi; jawaban yang bukan persetujuan
  dikembalikan ke model. Default `never`, supaya job terjadwal (F41) tetap jalan tanpa user.
- **Image.** `docker/sandbox.Dockerfile` (Python 3.12 + numpy, pandas, matplotlib dipin, `MPLBACKEND=Agg`,
  HOME dan cache di `/tmp`). Library analisa tidak ada di image service.

### Data source (F39)

```text
datasources.yaml (DATA_SOURCES_FILE) ── id, description, url_env ──► DataSourceRegistry
                                                                       (open di lifespan)
project.settings.data_source_ids ──► configurable ──► DataToolkit.tools_for(config)
  list_data_sources · search_schema · describe_table · profile_table · run_sql
      └─ DataAccess.source(config, id): hanya data source project ─► SqlDataSource
            pool psycopg, koneksi read-only, statement_timeout lokal per query
  run_sql: QueryGuard (sqlglot) ─► SELECT * FROM (...) LIMIT max+1 ─► Parquet ─► data/<name>.parquet
```

- **Registry dari file, DSN dari env.** `load_entries` membaca `DATA_SOURCES_FILE` (file tidak ada
  = tanpa data source, file rusak = startup gagal). DSN dibaca `EnvReader` (`core/env.py`, env proses
  lalu `.env`) dari nama di `url_env`. Env kosong atau database tidak terjangkau membuat data source
  itu *unavailable* dengan alasan yang aman ditampilkan, dan service tetap start.
- **Pertahanan berlapis** (ADR 0007). Pertama, user database read-only (pertahanan utama; dataset
  demo memakai role `analyst_ro` tanpa hak tulis). Kedua, koneksi pool di-set read-only, jadi setiap
  transaksi `READ ONLY` dengan `statement_timeout` lokal (`SQL_TIMEOUT_SECONDS`). Ketiga, `QueryGuard`
  menerima tepat satu query (`SELECT`/`UNION`/`WITH`), menolak node yang menulis di mana pun (termasuk
  CTE), `SELECT INTO`, `FOR UPDATE`, dan fungsi `pg_*`/`lo_*`/`dblink*`/`nextval`/`set_config`, lalu
  membungkusnya dengan `LIMIT SQL_MAX_ROWS + 1` untuk mendeteksi pemotongan.
- **Akses per project.** Tool data di-bind hanya pada giliran yang project-nya punya
  `data_source_ids` (pola skill), dan `DataAccess.source` menolak ID di luar daftar project walaupun
  terdaftar di registry. Project memvalidasi ID terhadap registry (tidak dikenal → 422); data source
  yang terdaftar tetapi unavailable tetap boleh dipilih.
- **Identifier tidak dirangkai mentah.** `SchemaInspector.resolve` mencocokkan nama tabel dari model
  ke `pg_catalog` (hanya tabel dengan hak `SELECT`) sebelum di-quote. Nilai dari model memakai
  parameter `%s`.
- **Profil.** `TableProfiler` exact sampai `PROFILE_EXACT_MAX_ROWS` (perkiraan `reltuples`), di
  atasnya `TABLESAMPLE SYSTEM`; output memperingatkan bahwa nilai langka bisa terlewat. Statistik per
  kolom mengikuti `typcategory`: min/max untuk angka, tanggal, dan teks; nilai teratas untuk teks dan
  boolean.
- **Hasil ke workspace.** `run_sql` menyimpan semua baris (sampai batas) sebagai Parquet
  (`datasource/results.py`, tipe yang tidak dikenal Arrow menjadi teks), dan model menerima tipe
  kolom serta pratinjau 20 baris. Sandbox memuat file itu tanpa kredensial database.
- **Domain-agnostic** (NFR-13). Tool dan deskripsinya tidak menyebut domain apa pun. Dataset demo
  (`docker/demo/`) hanya fixture: SQL deterministik (`setseed`), pola tertanam, dan kunci jawaban
  `planted_patterns.yaml` yang dicek test.

## Agent dengan Tool

`ToolCallingAgent` (`agents/tool_calling.py`) adalah agent generik yang dikonfigurasi lewat daftar
tool dan system prompt. Graph-nya `agent → tools → agent`: node `agent` memanggil model dengan
tool yang sudah di-bind, `tools_condition` mengarahkan tool call ke `ToolNode`, lalu hasilnya kembali
ke model sampai model menjawab tanpa tool call.

- **System prompt dirakit `ContextBuilder`** setiap kali model dipanggil (lihat
  [System Prompt](#system-prompt)). System message tidak disimpan di riwayat.
- **`ToolException`** dari tool dikembalikan ke model sebagai `ToolMessage` berstatus `error`, jadi
  model bisa mencoba lagi. Exception lain tetap menggagalkan run. Penyaringnya callable
  `tool_error_text` (`harness/tool_guard.py`), bukan tuple: dengan `awrap_tool_call`, `ToolNode`
  mengubah exception apa pun yang keluar dari wrapper menjadi pesan error tanpa memeriksa tipenya.
- **Batas langkah dan retry (FR-59, F47).** Service selalu mengisi `recursion_limit` di config run
  dari `AGENT_RECURSION_LIMIT` (default 50, ±24 putaran tool), dan sub-agent supervisor mewarisinya.
  Jika sisa langkah kurang dari `MIN_REMAINING_STEPS`, model tidak boleh memanggil tool baru dan
  menjawab `STEP_LIMIT_MESSAGE`. Graph yang tetap melewati limit menjadi `AgentStepLimitError`.
- **`ToolFailureGuard`** membungkus setiap tool call (di luar `ToolOutputOffloader`). Kegagalan
  beruntun dihitung per nama tool dari message sejak pesan human terakhir, bukan counter di memori,
  jadi tetap benar setelah resume interrupt. Kegagalan = `ToolMessage` berstatus `error`
  (`ToolException`, atau exit code bukan nol / timeout yang ditandai `run_python`/`run_shell`), dan
  hasil sukses me-reset hitungan. Setelah `TOOL_MAX_CONSECUTIVE_ERRORS` (default 3), tool tidak
  dijalankan dan model menerima `ToolMessage` error yang memintanya berhenti mencoba dan menjelaskan
  error ke user. Tool call paralel dalam satu jawaban membaca state yang sama, jadi tidak saling
  menghitung.
- **Tool** ditulis sebagai function `@tool` di `agents/tools/`. Docstring-nya berbahasa Inggris
  karena menjadi deskripsi tool untuk model. Tool dengan dependency (misalnya mesin pencari) dibuat
  lewat factory yang menerima dependency tersebut, supaya test bisa memakai tiruan tanpa network.

`research-assistant` (`agents/research.py`) adalah `ToolCallingAgent` dengan `web_search`
(Firecrawl Search API) dan `calculator` (numexpr).

Tool `web_search` memakai `SearchBackend` async yang di-inject. `create_app` membuatnya dari
`FIRECRAWL_API_KEY` (`build_search_backend`): `FirecrawlSearch` (satu `httpx.AsyncClient`,
`POST /v2/search`, hanya hasil web tanpa scraping) jika key ada, atau `UnconfiguredSearch` jika
kosong. Pada kasus kedua, tool menjawab "not configured" dan agent tetap berjalan. Error
pencarian (koneksi, 401/402/429, respons rusak) menjadi `SearchError` → `ToolException`, lalu
dikembalikan ke model.

## Human-in-the-loop

`InterruptAgent` (`agents/interrupt.py`) menunjukkan pola `interrupt()` yang dipakai ulang:

```text
START ─► (data sudah ada?) ─ya─► respond ─► END
             │ tidak
             ▼
          extract ─► (valid?) ─ya─► respond
             ▲           │ tidak
             └── ask ◄───┘   ask memanggil interrupt(pertanyaan)
```

- **`ask_birthdate`** memanggil `interrupt(pertanyaan)`. Service mengirim pertanyaan itu sebagai
  message AI. Giliran user berikutnya di thread yang sama dikirim sebagai `Command(resume=...)`
  (`build_run_input`), sehingga node yang sama dijalankan ulang dan `interrupt()` mengembalikan
  jawaban user. Jawaban itu dikembalikan sebagai `HumanMessage` baru, tanpa memutasi state.
- **Ulangan** terjadi lewat edge `ask → extract`, bukan rekursi.
- **Panggilan LLM internal** (ekstraksi terstruktur) diberi tag `skip_stream`, sehingga tidak muncul
  sebagai token. Hasilnya juga tidak disimpan sebagai message.
- **Data yang sudah valid** disimpan di state thread, sehingga giliran berikutnya langsung ke
  `respond`.

## Multi-agent (Supervisor)

`SupervisorAgent` (`agents/supervisor.py`) adalah graph `supervisor ⇄ delegate`:

- **`supervisor`** adalah LLM dengan satu tool delegasi `ask_<expert>(task)` per `Expert`. Node ini
  hanya melihat message tanpa penanda sub-agent, jadi urutan tool call dan hasilnya tetap valid.
- **`delegate`** menjalankan graph stateless milik expert (`ToolCallingAgent.build_stateless`) dengan
  model yang sama dari request (FR-4) dan tag run `subagent`. Setiap message expert ditandai
  `additional_kwargs["subagent"]`, dikirim bertahap lewat `get_stream_writer()`, lalu disimpan.
  Jawaban akhir expert dikembalikan ke supervisor sebagai `ToolMessage`.
- **Converter** mengubah penanda itu menjadi `ChatMessage.agent`. `StreamService` tidak mengalirkan
  token dari run bertag `subagent`, dan mengirim message expert sekali saja (dedupe per `id`).
- **UI** merender message ber-`agent` di kontainer berbingkai bernama expert, baik saat live maupun
  di riwayat.

## Menambah Agent

1. **Buat subclass `BaseAgent`** di `src/agent_service/agents/`. Node yang membutuhkan model ditulis
   sebagai closure di dalam `build()`, karena satu instance agent membangun graph untuk beberapa
   model.

   ```python
   class SummarizerConfig(BaseModel):
       model_config = ConfigDict(extra="forbid", json_schema_extra={"description": "Summary options."})
       max_sentences: int = 3


   class SummarizerAgent(BaseAgent):
       config_schema = SummarizerConfig

       def __init__(self) -> None:
           super().__init__(agent_id="summarizer", description="Summarizes the conversation.")

       def build(
           self, model: BaseChatModel, checkpointer: Checkpointer, store: BaseStore | None = None
       ) -> AgentGraph:
           async def summarize(state: MessagesState, config: RunnableConfig) -> MessagesState:
               limit = config["configurable"]["max_sentences"]
               prompt = SystemMessage(f"Summarize in at most {limit} sentences.")
               return {"messages": [await model.ainvoke([prompt, *state["messages"]])]}

           builder = StateGraph(MessagesState)  # pyrefly: ignore[bad-specialization]
           builder.add_node("summarize", summarize)
           builder.add_edge(START, "summarize")
           builder.add_edge("summarize", END)
           return builder.compile(checkpointer=checkpointer)
   ```

   Override `build` wajib membawa semua parameter induk, termasuk `store` (dipakai agent yang
   memerlukan long-term memory). Untuk agent dengan tool, prompt dari `ContextBuilder`, skill, atau
   tool file, lebih sederhana membuat instance `ToolCallingAgent` daripada subclass baru.
2. **Tulis deskripsi publik `config_schema` secara eksplisit dalam bahasa Inggris**
   (`json_schema_extra`). Docstring model ikut tampil di `/info`. Agent tanpa opsi cukup memakai
   `EmptyAgentConfig` bawaan.
3. **Override `async load()`** jika agent butuh resource async, misalnya koneksi MCP. Kegagalan di
   sini hanya membuat agent tersebut unavailable.
4. **Daftarkan agent** di `create_default_agents()` (`agents/catalog.py`).
5. **Tulis test** dengan `FakeModel(responses=[...])`. Respons bisa berisi `tool_calls`. Untuk
   test endpoint, tambahkan agent lewat `create_app(settings, agents=[...])` seperti di
   `tests/service/conftest.py`.

## Client

`AgentClient` (`client/`) hanya bergantung pada `schema/`, httpx, dan pydantic. Aturan ini dicek
oleh `tests/client/test_layering.py`.

- **Tidak ada request di konstruktor.** `get_info()` diambil saat pertama dipakai lalu di-cache.
- **Login.** `login(username, password)` menyimpan access token di client dan mengirimkannya sebagai
  `Authorization: Bearer` di setiap request berikutnya. Identitas user selalu dari token.
- **`invoke`** mengembalikan `AgentReply`, berisi message beserta `thread_id` dari header
  `X-Thread-Id`.
- **Selain chat**, client membungkus thread, project, skill, memory, trace, dan artifact
  (upload/unduh), semuanya dengan pasangan sync/async.
- **`stream`** mengembalikan `StreamRun`. Request dikirim saat masuk `with`, sehingga error
  404/422 dilempar di situ sebagai `AgentClientError`. Event berupa model `StreamEvent` yang sama
  dengan milik service. Frame `error` diteruskan sebagai `ErrorEvent`, dan stream yang berakhir
  tanpa `[DONE]` dianggap error.
- **Satu `RequestSpec` per operasi.** Spec ini dipakai bersama oleh method sync dan async
  (berawalan `a`).

## UI

`ui/` adalah **dev console** Streamlit (FR-45): fitur baru tidak ditambahkan di sini, dan UI utama
adalah [Frontend](#frontend) React. `ui/` hanya bergantung pada `client/`, `schema/`, streamlit, dan
pydantic. Aturan ini dicek oleh `tests/ui/test_layering.py`.

- **`app.py`** dijalankan ulang oleh Streamlit pada setiap interaksi. `UiSettings` membaca
  `AGENT_URL`. Setiap session browser punya `AgentClient` sendiri, karena `agent_id` dan access
  token-nya milik session tersebut. Tanpa login, hanya `LoginView` yang tampil.
- **`login_view.py`** berisi form login, tombol logout di sidebar, dan `end_expired_session`: respons
  401 di tengah sesi mengembalikan user ke form login dengan pesan. Logout menghapus token, username,
  dan `ChatSession`.
- **`UrlState`** menyimpan `thread_id` dan `agent` di query param (param `user_id` lama dihapus saat
  URL ditulis). `ChatSession` dibangun dari URL saat session dimulai, lalu ditulis kembali ke URL di
  akhir setiap run.
- **`ChatSession`** (`st.session_state`) menyimpan thread, agent, model, opsi token, dan message
  yang sudah tampil. Thread dari URL dimuat riwayatnya sekali.
- **`SidebarView`** berisi tombol chat baru, pemilih agent dan model dari `/info`, toggle streaming,
  dan daftar thread (`st.cache_data` dengan `THREAD_LIST_CACHE_TTL_SECONDS`, dengan username sebagai
  bagian kunci cache, karena cache Streamlit berlaku untuk seluruh proses) beserta aksi rename dan
  hapus. Pilihan disimpan lewat callback widget sebelum script diulang.
- **`ChatView`** memutar ulang riwayat, lalu men-stream jawaban baru. Pesan user baru disimpan
  setelah service menerima request.
- **`MessageRenderer`** punya satu method per tipe message. Jawaban AI, tool call, dan hasil tool
  berurutan digabung dalam satu blok chat, dengan tool call tampil sebagai `st.status`.

## Reasoning Model

Model reasoning menulis pemikirannya di field stream non-standar (`reasoning` di Ollama,
`reasoning_content` di vLLM/DeepSeek). `ReasoningChatOpenAI` (`llm/reasoning.py`) menyalinnya ke
`additional_kwargs["reasoning_content"]` di setiap chunk. `StreamService` mengubahnya menjadi frame
`reasoning`, dan LangChain menggabungkan potongannya sehingga message akhir di checkpoint berisi
reasoning lengkap. Converter mengisi `ChatMessage.reasoning`, dan UI menampilkannya di blok
"Thinking" (terbuka saat live, tertutup di riwayat). Hanya field standar yang dikirim balik ke
model, jadi reasoning lama tidak ikut di prompt giliran berikutnya.

## Batas Token Jawaban

`ModelFactory.create(name, max_tokens=None)` membuat model dengan batas token jawaban
`LLM_MAX_TOKENS` (`DEFAULT_LLM_MAX_TOKENS`), atau nilai `max_tokens` jika diberikan. Kunci cache
adalah `(nama model, max_tokens)`, sehingga override per Project (F26) mendapat instance sendiri.
`ChatOpenAI` selalu menulisnya sebagai `max_completion_tokens`, padahal Ollama hanya membaca
`max_tokens`. Karena itu `ReasoningChatOpenAI._get_request_payload` mengganti namanya sesuai
`LLM_MAX_TOKENS_PARAM` (default `max_tokens`; `max_completion_tokens` untuk model reasoning OpenAI
yang menolak `max_tokens`). Pada Ollama, token reasoning ikut dihitung dalam batas ini, jadi batas
yang terlalu kecil bisa menghasilkan jawaban kosong yang ditandai terpotong.

Jika model berhenti karena batas, provider mengirim `finish_reason = "length"`, dan LangChain
menyimpannya di `response_metadata` message AI. Converter (`is_truncated`) mengubahnya menjadi
`ChatMessage.truncated = true`, jadi tanda ini muncul sama di `/invoke`, frame `message` `/stream`,
dan `/history`. UI menampilkan peringatan di bawah jawaban. `FakeModel` meneruskan
`response_metadata` hasil script, baik lewat `invoke` maupun streaming, untuk menguji jalur ini.

## Deployment

Image:

| File | Target | Isi |
|---|---|---|
| `docker/Dockerfile` | `service` | `python -m agent_service.run_service`, juga dipakai service `migrate`. Extra `service` dan `analytics` (sqlglot, pyarrow) |
| `docker/Dockerfile` | `sandbox-runner` | Runner sandbox (F37), satu-satunya yang me-mount `docker.sock` |
| `docker/Dockerfile` | `ui` | Dev console Streamlit. Extra `ui` saja |
| `docker/sandbox.Dockerfile` | – | Image eksekusi kode: Python + numpy, pandas, matplotlib |
| `frontend/Dockerfile` | `web` | Build React, disajikan nginx unprivileged + proxy `/api` |

Setiap target Python meng-install hanya extra miliknya (`uv sync --frozen --no-dev --extra
service` atau `--extra ui`), sehingga image service tanpa Streamlit dan image UI tanpa LangGraph.
Test e2e `test_image_ships_only_its_extra` menjaga batas ini.

`compose.yaml`:

```text
postgres (healthy) ──► migrate (selesai) ─────────┐
postgres (healthy) ──► demo-seed (selesai) ────────┤
sandbox-image (build lalu selesai)                 ├──► agent-service (healthy) ──► web :3000, ui :8501
sandbox-runner (healthy, tanpa port host) ─────────┘
volume: postgres-data (database), artifacts (isi file artifact)
```

Service memakai FakeModel secara default. `compose.llm.yaml` menimpa konfigurasi model dengan LLM
asli.

`demo-seed` (image postgres, `docker/demo/seed.sh`) membuat database `demo_shop` dan `demo_sensors`
di server yang sama, mengisinya dari SQL deterministik, dan membuat role login `analyst_ro` yang
hanya punya `SELECT`. Service ini idempotent: tabel demo dibuat ulang setiap kali dijalankan.

## Testing

- **Tidak ada network di unit test.** Fixture autouse `block_network` (`tests/conftest.py`)
  menggagalkan koneksi selain loopback.
- **Database test memakai Postgres asli.** Fixture sesi `postgres_database` membuat database
  `agent_service_test_<acak>` dan memigrasinya, fixture `database_url` mengosongkan tabel sebelum
  setiap test, dan database dihapus di akhir sesi. Fixture autouse `isolate_database_url`
  mengarahkan `DATABASE_URL` ke host yang tidak ada, supaya test tidak pernah menulis ke database
  dev. Test murni (agent dengan `InMemorySaver`) tidak butuh database.
- **Dataset demo di test.** Fixture sesi `demo_database_urls` membuat kedua database demo dari
  `docker/demo/*.sql` dan role read-only acak, lalu menghapusnya di akhir sesi. Fixture autouse
  `isolate_data_sources` mengarahkan `DATA_SOURCES_FILE` ke file yang tidak ada, jadi
  `datasources.yaml` repo dan DSN di `.env` tidak terbaca.
- **LLM diganti `FakeModel`.** Model ini men-stream per kata dan mengirim `tool_calls` utuh, dan
  setiap panggilan mengembalikan salinan message baru.
- **Test endpoint memakai `httpx.AsyncClient` + `ASGITransport`.** Lifespan dijalankan manual
  dengan `app.router.lifespan_context(app)`, karena `ASGITransport` melewatinya.
- **Client dites dua kali:** dengan `httpx.MockTransport`, dan sebagai test kontrak terhadap app
  asli lewat `httpx.ASGITransport` (`tests/client/test_client_contract.py`).
- **UI dites dengan `streamlit.testing.v1.AppTest`.** Test menyuntikkan `AgentClient` dengan
  `httpx.MockTransport` lewat `st.session_state[CLIENT_OVERRIDE_KEY]`.
- **Test e2e bermarker `integration`** (`tests/integration/`) menjalankan stack Compose sungguhan.
  Test ini dilewati `pytest` default, dan dijalankan dengan `pytest -m integration` serta job CI
  `e2e`.
- **pytest memakai `--import-mode=importlib`.** Akibatnya file test tidak saling import, dan fake
  bersama disediakan lewat fixture.
- **Aturan arsitektur dites otomatis:** layering per package (`tests/*/test_layering.py`), larangan
  eksekusi kode di proses service (`tests/test_no_code_execution.py`, NFR-10), dan kontrak API
  yang usang (`export_contracts --check`).
- **Eval:** `tests/evals/test_datasets.py` memvalidasi semua dataset dan menjalankan
  `evals/smoke.yaml` dengan FakeModel.
- **Frontend dites dengan Vitest** (jsdom) dari `frontend/` (`corepack pnpm test`), dengan rekaman
  SSE asli di `src/features/chat/__fixtures__/`. `corepack pnpm run check` mencocokkan tipe API
  dengan `contracts/`, lalu menjalankan `tsc` dan ESLint.
