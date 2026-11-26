# PRD: LangGraph Agent Service (Rewrite)

| | |
|---|---|
| Status | Draft |
| Versi dokumen | 0.3 (sinkron dengan `v0.7.0`) |
| Tanggal | 2026-11-01, direvisi 2026-11-15 dan 2026-11-19 |
| Referensi | `agent-service-toolkit/` (kode asli), [docs/adr/](docs/adr/) (keputusan arsitektur), [docs/DATA_MODEL.md](docs/DATA_MODEL.md) (skema data) |

**Fase 1 (v1, M1–M3)** selesai di `v0.3.0`. **Fase 2 (M4–M11)** mengubah service menjadi produk
chat dengan Project, skill, file, eksekusi kode, analisa data, RAG, dan frontend React. M4–M7
(FR-30–FR-50) sudah dirilis di `v0.7.0`. M8–M11 (FR-51–FR-62) belum dikerjakan. Requirement fase 2
ada di §5 bagian "Fase 2" (FR-30 dan seterusnya). Analisa data (M8) direvisi 2026-11-26 menjadi
strategi code-as-action ([ADR 0006](docs/adr/0006-data-catalog-semantic-layer.md),
[ADR 0007](docs/adr/0007-code-as-action-execution.md)).

## 1. Latar Belakang

`agent-service-toolkit` adalah template lengkap untuk menjalankan agent LangGraph sebagai service
(FastAPI + Streamlit). Template ini kaya fitur, tetapi sulit dirawat dan dikembangkan karena:

- **Side effect saat import.** `Settings()` raise jika tidak ada API key (`core/settings.py:262`),
  graph di-compile dan model dibuat di level modul (`agents/langgraph_supervisor_agent.py:8`).
  Akibatnya, model yang dipilih user diabaikan oleh agent supervisor, dan test sulit diisolasi.
- **Global state yang dimutasi.** Registry `agents` adalah dict global (`agents/agents.py:34`), dan
  checkpointer ditempel ke graph setelah compile (`service/service.py:112-114`).
- **Duplikasi.** `research_assistant.py` dan `rag_assistant.py` ~90% identik, request di
  `client/client.py` dibangun ulang 4 kali, dan `model_post_init` di `core/settings.py:178-251`
  mengulang pola yang sama 12 kali.
- **Fungsi panjang dan nesting dalam.** `message_generator` sekitar 110 baris dengan nesting 6+
  level (`service/service.py:243-353`). Fungsi `main()` dan `draw_messages` di Streamlit
  bersama-sama ±450 baris.
- **Error handling terlalu luas.** Ada 22 `except Exception`. Agent tidak dikenal menghasilkan 500,
  bukan 404 (`service/service.py:217`).
- **Magic number** tersebar: `k=5`, `timeout=60`, `ttl=600`, `remaining_steps < 2`, dan
  `temperature=0.5` (9 kali).
- **Scope terlalu luas** untuk kebutuhan kami: 12 provider LLM, 3 backend DB, voice, AG-UI,
  Langfuse, LangSmith.

Rewrite ini mempertahankan inti yang berguna (agent registry, API invoke/stream, client, UI) dan
membangunnya ulang dengan prinsip Zen of Python serta desain berbasis class (lihat
[AGENTS.md](AGENTS.md)).

## 2. Tujuan

1. Service yang bisa menjalankan **beberapa agent LangGraph** lewat satu API.
2. **Streaming token dan message** via SSE yang stabil dan teruji.
3. **Mudah menambah agent baru**: subclass `BaseAgent`, register, selesai. Tidak perlu menyentuh
   service atau UI.
4. Kode yang **mudah dibaca dan dites**: tanpa side effect saat import, tanpa global yang dimutasi,
   dependency eksplisit.

**Tujuan Fase 2:**

5. **Showcase produk** dengan frontend React bergaya Claude: Projects, chat, dan panel artifact.
6. **Project sebagai agent deklaratif** (instruksi, skill, model, knowledge) yang bisa dibuat user
   tanpa menulis kode ([ADR 0004](docs/adr/0004-project-as-declarative-agent.md)).
7. **Lapisan harness** milik sendiri: prompt dirakit setiap giliran, skill dengan progressive
   disclosure, context management, dan long-term memory
   ([ADR 0002](docs/adr/0002-own-harness.md)).
8. **Analisa data** dari database relasional, termasuk laporan PDF terjadwal, dengan eksekusi kode
   yang selalu terisolasi di sandbox. Agent dibangun dari primitif generik (eksplorasi data, query,
   kernel iteratif), pengetahuan (data catalog dan playbook metode), dan loop kerja (rencana,
   verifikasi, batas retry), bukan satu fungsi per skenario. Coverage diukur dengan eval lintas
   dataset.
9. **RAG** dengan pipeline ingestion lengkap, per Project.

## 3. Non-Goals (v1)

- Banyak provider LLM sekaligus. v1 hanya memakai endpoint OpenAI-compatible + FakeModel.
- Backend persistence selain SQLite.
- Voice (STT/TTS), AG-UI protocol, Langfuse/LangSmith tracing dan feedback.
- Safeguard/prompt-injection classifier.
- Multi-tenant auth (user management, OAuth). v1 hanya memakai shared bearer token.
- Deployment cloud. v1 cukup Docker Compose lokal.

**Revisi Fase 2:** backend persistence berubah menjadi Postgres-only (FR-32), dan auth per user
masuk scope (FR-33). Non-goals yang tetap berlaku di Fase 2:

- Banyak provider LLM. Tetap satu jalur OpenAI-compatible (embedding juga).
- Self-registration, reset password, dan SSO/OIDC. User demo dibuat lewat CLI (SSO di backlog B6).
- Skill dan job terjadwal yang dibuat lewat UI (backlog B1 dan B2). Desainnya tetap disiapkan.
- Sandbox production (managed atau self-hosted). Fase 2 memakai sandbox Docker untuk dev dan demo
  (backlog B5).
- Voice. Pemisahan produk chat dari dev-time harness (masih ide, tidak dijadwalkan).

## 4. Persona

| Persona | Kebutuhan |
|---|---|
| **Agent developer** | Menulis agent LangGraph baru dan langsung bisa mencobanya lewat API/UI tanpa memahami internal service. |
| **Integrator** | Memanggil agent dari aplikasi lain lewat HTTP atau `AgentClient`. |
| **End user** | Chat dengan agent di browser, melihat jawaban mengalir, melanjutkan percakapan lama. |
| **Project builder** (Fase 2) | Membuat Project dengan instruksi, skill, dan knowledge sendiri tanpa menulis kode. |
| **Data analyst** (Fase 2) | Bertanya tentang data di database, mendapat tabel, chart, dan laporan PDF terjadwal. |

## 5. Functional Requirements

### Agent & Registry

- **FR-1** `AgentRegistry` menyimpan agent berdasarkan `agent_id` unik, beserta deskripsinya.
  Registry dibuat di lifespan, bukan saat import.
- **FR-2** `BaseAgent` mendefinisikan kontrak: `agent_id`, `description`, dan
  `build(model, checkpointer) -> CompiledStateGraph`. Agent yang butuh inisialisasi async
  (misalnya MCP) meng-override `async load()`.
- **FR-3** Agent di-compile dengan checkpointer saat startup, setelah `load()` berhasil. Agent yang
  gagal load dicatat di log dan ditandai *unavailable*, tetapi service tetap jalan.
- **FR-4** Model yang dipilih per request harus benar-benar dipakai oleh agent, termasuk sub-agent
  supervisor.

### Agent v1

| `agent_id` | Deskripsi | Mendemonstrasikan |
|---|---|---|
| `chatbot` | Satu panggilan LLM dengan riwayat percakapan | Agent minimal |
| `research-assistant` | `ToolCallingAgent` dengan web search + calculator | Tool calling loop |
| `interrupt-agent` | Menanyakan info yang kurang ke user, lalu melanjutkan | `interrupt()` + resume |
| `supervisor` | Supervisor dengan 2 sub-agent (math, research) | Multi-agent + subgraph streaming |

`research-assistant` dan RAG lama digabung menjadi satu class `ToolCallingAgent` yang dikonfigurasi
lewat daftar tools. RAG cukup menjadi instance lain dengan tool retriever (Future).

### API

- **FR-5** `GET /info` mengembalikan daftar agent yang tersedia (agent yang gagal load tidak
  ditampilkan), agent default (`chatbot`), daftar model, dan model default.
- **FR-6** `POST /{agent_id}/invoke` menjalankan agent sampai selesai dan mengembalikan
  `ChatMessage` terakhir.
- **FR-7** `POST /{agent_id}/stream` mengalirkan event SSE (lihat §7.3). Request yang tidak valid
  (agent/model tidak dikenal, `agent_config` salah, thread milik user lain) dijawab dengan status
  HTTP biasa sebelum stream dimulai. Error di tengah run menjadi frame `error` dengan pesan
  generik, lalu `[DONE]`.
- **FR-8** `POST /{agent_id}/history` mengembalikan riwayat message satu thread. Request wajib
  menyertakan `user_id`. Thread milik user lain diperlakukan sebagai tidak ada (404), sama dengan
  FR-25/26.
- **FR-9** `GET /{agent_id}/threads?user_id=...` mengembalikan daftar thread milik user (judul,
  waktu update), yang terakhir di-update lebih dulu, dibatasi `limit` (1–100, default 20). Judul
  diambil dari message human pertama, atau `Untitled thread` jika belum ada.
- **FR-25** `PATCH /{agent_id}/threads/{thread_id}` mengganti judul thread (`{"user_id", "title"}`).
  Judul custom disimpan terpisah dari checkpoint dan menimpa judul otomatis. Hanya pemilik thread
  yang boleh mengganti judul. Thread milik user lain diperlakukan sebagai tidak ada (404).
- **FR-26** `DELETE /{agent_id}/threads/{thread_id}?user_id=...` menghapus thread: semua checkpoint
  (`checkpointer.adelete_thread`) dan metadata judulnya. Aturan kepemilikan sama dengan FR-25.
  Response 204. Setelah dihapus, `/history` thread itu menjawab 404 dan ID-nya boleh dipakai
  untuk thread baru.
- **FR-10** `GET /health` selalu tanpa auth.
- **FR-11** Jika `AUTH_SECRET` diset, semua endpoint kecuali `/health` membutuhkan
  `Authorization: Bearer <AUTH_SECRET>`. *Digantikan FR-33 mulai F24.*
- **FR-12** Jika thread sedang dalam status `interrupt`, input berikutnya dikirim sebagai
  `Command(resume=...)`.
- **FR-13** `thread_id` dan `user_id` yang kosong diisi UUID baru dan dikembalikan ke client lewat
  header response `X-Thread-Id` dan `X-User-Id` (`/invoke` dan `/stream`).
- **FR-28** Thread yang sudah ada hanya bisa dilanjutkan (`/invoke`, `/stream`) dan dibaca
  (`/history`) oleh user dan agent yang membuatnya. Selain itu → 404. Kepemilikan dicek dari
  metadata checkpoint (`user_id`, `agent_id`).
- **FR-14** `model` divalidasi terhadap allowlist `AVAILABLE_MODELS`. Model tidak dikenal → 422.
- **FR-15** `agent_id` tidak dikenal → 404. Agent unavailable → 503.
- **FR-27** `agent_config` divalidasi **per agent**. Setiap agent mendeklarasikan
  `config_schema: type[BaseModel]` (default: model kosong dengan `extra="forbid"`). Config yang
  tidak valid → 422 dengan detail field. Config yang sudah divalidasi diteruskan ke graph lewat
  `RunnableConfig["configurable"]`. `/info` menyertakan JSON Schema config milik setiap agent.

### Persistence

- **FR-16** Checkpointer SQLite (`AsyncSqliteSaver`) dengan path dari `SQLITE_DB_PATH`. Dibuka di
  lifespan, ditutup saat shutdown. *Digantikan FR-32 mulai F23.*

### Client

- **FR-17** `AgentClient` menyediakan method sync dan async (berawalan `a`): `invoke`, `stream`,
  `get_history`, `get_threads`, `rename_thread`, `delete_thread`, `get_info`. `invoke`
  mengembalikan `AgentReply(message, thread_id, user_id)`. `stream` adalah context manager
  (`StreamRun`) yang punya `thread_id`/`user_id` dan menghasilkan `StreamEvent`. Frame `error`
  diteruskan sebagai `ErrorEvent`, bukan exception.
- **FR-18** Error HTTP dibungkus menjadi `AgentClientError` dengan status code dan pesan.
- **FR-19** Tidak ada network call di konstruktor `AgentClient`. `/info` diambil secara lazy.

### UI (Streamlit)

- **FR-20** Chat dengan streaming token, menampilkan tool call sebagai status box yang bisa
  di-expand.
- **FR-21** Sidebar: tombol chat baru, daftar thread sebelumnya (dengan aksi rename dan hapus),
  pemilih agent dan model, toggle streaming.
- **FR-22** `user_id`, `thread_id`, dan `agent` disimpan di URL query param sehingga percakapan dan
  daftar thread bisa dibuka ulang. `user_id` ikut disimpan karena service hanya membuka thread
  untuk pemiliknya (FR-28). Siapa pun yang memegang URL lengkap bisa membaca thread tersebut, sesuai
  v1 yang belum punya auth per user.
- **FR-23** Menampilkan handoff sub-agent (supervisor) secara bertingkat. Message buatan sub-agent
  membawa `ChatMessage.agent` (nama expert), dikirim bertahap selama expert bekerja, dan tetap
  bertingkat saat thread dibuka ulang.
- **FR-24** Saat agent meminta input (interrupt), pertanyaannya ditampilkan sebagai pesan AI biasa.
- **FR-29** Jika model mengirim reasoning (token pemikiran), service meneruskannya sebagai frame SSE
  `reasoning` sebelum token jawaban, dan UI menampilkannya di blok "Thinking" yang bisa
  dibuka-tutup, supaya jeda saat model berpikir tidak terlihat seperti idle. Reasoning disimpan
  di riwayat (`ChatMessage.reasoning`) dan tampil tertutup saat thread dibuka ulang.
  `stream_tokens=false` juga mematikan frame `reasoning`. Model tanpa reasoning tidak terpengaruh.

### Fase 2: Foundation (M4)

- **FR-30** Batas token jawaban. `LLM_MAX_TOKENS` (default di `Settings`) bisa ditimpa per Project.
  Batas ini mencakup token reasoning pada provider yang menghitungnya bersama. Message AI yang
  berhenti karena batas (`finish_reason = "length"`) ditandai `ChatMessage.truncated = true`, dan UI
  menampilkan peringatan "jawaban terpotong".
- **FR-31** Dependency dipisah menjadi extras (`service`, `ui`, `analytics`, `rag`). Image Docker
  hanya memasang extras yang dibutuhkan target-nya. Dev dan CI memasang semua extras.
- **FR-32** Postgres adalah satu-satunya database ([ADR 0001](docs/adr/0001-postgres-only.md)).
  Checkpointer `AsyncPostgresSaver` dan tabel aplikasi (SQLAlchemy Core + Alembic) memakai
  `DATABASE_URL`. Postgres berjalan sebagai service `postgres` di `compose.yaml`, dan migrasi
  dijalankan oleh service `migrate` sebelum API start. Menggantikan FR-16.
- **FR-33** Auth per user. User login (`POST /auth/login`) dan menerima JWT access token. `user_id`
  diambil dari token, bukan dari body/query (field `user_id` di request dihapus). User demo dibuat
  lewat CLI. Klien mesin (worker) memakai service account dengan token sendiri. `/health` tetap tanpa
  auth. Menggantikan FR-11 dan aturan `user_id` di FR-8, FR-9, FR-13, FR-22, FR-25, FR-26.
- **FR-34** CORS diizinkan hanya untuk origin di `CORS_ORIGINS`.
- **FR-35** Kontrak API dipublikasikan sebagai file di repo: `contracts/openapi.json` dan
  `contracts/stream-event.schema.json` (JSON Schema `StreamEvent`). CI gagal jika file tidak
  sinkron dengan kode. Tipe TypeScript frontend digenerate dari file ini.

### Fase 2: Harness Core (M5)

- **FR-36** Project ([ADR 0004](docs/adr/0004-project-as-declarative-agent.md)). CRUD `/projects`
  untuk project milik user, dan project built-in (read-only) yang di-seed saat startup. Project
  berisi `base_agent_id`, `model`, `instructions`, `skill_ids`, dan `settings` yang divalidasi.
  Setiap thread punya `project_id`, dan listing thread bisa difilter per project.
- **FR-37** System prompt dirakit setiap giliran oleh `ContextBuilder`, dengan urutan tetap: instruksi
  agent, instruksi project, indeks skill, memory user, ringkasan percakapan lama (FR-39), dan
  informasi lingkungan (tanggal, timezone). Setiap bagian punya batas ukuran.
- **FR-38** Skill built-in ([ADR 0005](docs/adr/0005-skill-format-and-sources.md)) berformat
  `SKILL.md` di `src/agent_service/skills/builtin/`. Skill divalidasi saat startup (yang tidak valid
  dilewati dan dicatat di log). `GET /skills` dan `GET /skills/{id}` (read-only). Tool
  `load_skill(name, path?)` hanya bisa memuat skill yang aktif di Project.
- **FR-39** Context management. Sebelum memanggil model, riwayat dipangkas ke anggaran
  `CONTEXT_MAX_TOKENS` (default 16.000, mencakup riwayat dan ringkasan). Saat anggaran terlampaui,
  giliran lama diringkas sekaligus sampai riwayat langsung tinggal ±50% anggaran, dan ringkasannya
  disimpan di state thread. Tool call dan hasilnya tidak pernah dipisah. Riwayat lengkap tetap
  tersedia di `/history`.
- **FR-40** Long-term memory per user (`AsyncPostgresStore`) untuk `chatbot` dan
  `research-assistant`. Hingga 20 memory terbaru masuk ke system prompt. Tool `search_memory`
  mencari dengan kata kunci, dan `save_memory` hanya menyimpan setelah user menyetujui lewat balasan
  teks pada interrupt ("yes"/"ya"; balasan lain menolak dan diteruskan ke model). Maksimal 200
  memory per user. User bisa melihat dan menghapus memory lewat `GET`/`DELETE /memories`.
- **FR-41** Evaluasi dan tracing. Dataset eval di `evals/` dijalankan lewat CLI (`run_evals`) dan
  menghasilkan laporan skor dengan cek deterministik (teks, tool, skill, latensi). LLM judge ditunda.
  Setiap run `/invoke` dan `/stream` mencatat trace (panggilan model, tool, token, latensi, status)
  di tabel Postgres `run_traces`, tanpa isi prompt/jawaban. Pemilik run membacanya lewat
  `GET /runs/{run_id}/trace`.

### Fase 2: Frontend (M6)

- **FR-42** Frontend React + TypeScript di `frontend/` ([ADR 0003](docs/adr/0003-frontend-stack.md))
  dengan komponen standar (shadcn/ui, assistant-ui). Dijalankan sebagai service `web` di
  `compose.yaml`. Ada halaman login.
- **FR-43** Chat: streaming token, blok reasoning yang bisa dibuka-tutup, status tool call,
  pertanyaan interrupt, langkah sub-agent yang bertingkat, dan peringatan jawaban terpotong.
- **FR-44** Layout ala Claude: sidebar (chat baru, Projects, Recents dengan rename/hapus), halaman
  Project (instruksi, model, pemilih skill, daftar chat), dan pembuatan Project.
- **FR-45** Streamlit menjadi dev console. Fitur baru tidak ditambahkan ke Streamlit, dan Streamlit
  dihapus setelah frontend setara (backlog B3).

### Fase 2: Files & Execution (M7)

- **FR-46** Artifact. File (upload user atau hasil agent) disimpan lewat `ArtifactStore` (volume
  lokal di fase 2), dengan metadata di Postgres. `ChatMessage.artifacts` berisi daftar
  `ArtifactRef {id, name, mime_type, size}`. `POST /artifacts` untuk upload,
  `GET /artifacts/{id}` untuk download (selalu `attachment`), dan `DELETE /artifacts/{id}`, hanya
  untuk pemiliknya. Ukuran dibatasi `ARTIFACT_MAX_BYTES` (default 25 MB). Upload dilampirkan ke
  pesan lewat `artifact_ids` di input run, dan artifact ikut terhapus saat thread-nya dihapus.
- **FR-47** Workspace (virtual filesystem) per thread di Postgres. Tool `read_file`, `write_file`,
  `edit_file`, `list_files`, dan `grep`. Path dinormalisasi dan tidak bisa keluar dari workspace.
- **FR-48** Output tool yang melebihi `TOOL_OUTPUT_MAX_TOKENS` (default 4.000) ditulis ke workspace.
  Model hanya menerima cuplikan dan path-nya. Lampiran pesan disalin ke workspace (`uploads/`), dan
  tool `share_file` membagikan file workspace sebagai artifact.
- **FR-49** Sandbox. Kode (`run_python`, `run_shell`) hanya dijalankan di dalam `Sandbox`, tidak
  pernah di proses service. Sandbox berjalan tanpa jaringan, dengan batas CPU, memori, jumlah proses,
  dan waktu. File workspace disalin masuk sebelum eksekusi, dan file baru atau berubah disalin
  kembali ke workspace (dibagikan sebagai artifact lewat `share_file`). `ProjectSettings.tool_approval`
  (`never`/`always`, default `never`) menentukan apakah eksekusi perlu persetujuan user (interrupt).
  Hanya service `sandbox-runner` yang memegang akses Docker.
- **FR-50** Panel artifact di frontend: preview gambar, tabel CSV, viewer PDF, dan tombol download.
  File dari composer di-upload saat dipilih dan dikirim sebagai `artifact_ids`; gambar markdown
  yang menyebut nama artifact di jawaban yang sama ditampilkan dari artifact itu.

### Fase 2: Analytics Core (M8)

Direvisi 2026-11-26 ([ADR 0006](docs/adr/0006-data-catalog-semantic-layer.md),
[ADR 0007](docs/adr/0007-code-as-action-execution.md)). Semua requirement di bawah bersifat
domain-agnostic: tidak ada nama domain di tool, prompt agent, atau skill.

- **FR-59** Batas langkah dan retry untuk semua agent. Setiap run memakai `recursion_limit`
  eksplisit (`AGENT_RECURSION_LIMIT`), bukan default LangGraph. Kegagalan beruntun pada tool yang
  sama (`ToolException`, serta exit code bukan nol atau timeout untuk tool eksekusi) dihitung. Setelah
  `TOOL_MAX_CONSECUTIVE_ERRORS` (default 3), tool itu tidak dijalankan lagi di giliran tersebut,
  dan model diminta menjelaskan error ke user. Error tetap dikembalikan ke model sebagai observasi.
  Run yang tetap melewati `recursion_limit` dijawab `/invoke` dengan 500 dan pesan step limit, dan
  `/stream` dengan frame `error` berisi pesan yang sama.
- **FR-51** Data source read-only dan primitif eksplorasi. Registry data source di
  `DATA_SOURCES_FILE` (DSN dari env, user database read-only). Project memilih data source lewat
  `ProjectSettings.data_source_ids`, dan tool hanya bisa mengakses data source project. Tool generik:
  `list_data_sources`, `search_schema`, `describe_table` (kolom, tipe, komentar, relasi, perkiraan
  jumlah baris, contoh baris), `profile_table` (null, distinct, min/max, nilai teratas, rentang
  tanggal), dan `run_sql`. `run_sql` hanya menerima satu `SELECT` (diparse `sqlglot`) di transaksi
  read-only, dengan batas baris dan `statement_timeout`, lalu menyimpan hasilnya sebagai Parquet di
  workspace. Sandbox tidak pernah menerima kredensial database. Ada dua dataset demo dari domain
  berbeda dengan pola yang sengaja ditanam. *Revisi dari FR-51 awal (satu `DATA_SOURCE_URL`, tiga
  tool).*
- **FR-60** Data catalog sebagai semantic layer terstruktur: satu file YAML per data source berisi
  deskripsi tabel dan kolom, metrik (ekspresi, grain, kolom waktu, filter, unit), dimensi, join, dan
  catatan kualitas data. Katalog divalidasi terhadap skema database saat startup. Katalog yang tidak
  valid membuat data source itu unavailable, tanpa menggagalkan service. Tool `list_metrics` dan
  `get_metric`. Katalog bersifat opsional.
- **FR-61** Kernel Python per thread untuk `run_python`: variabel dan import bertahan antar
  pemanggilan di thread yang sama. Isolasinya sama dengan FR-49 (tanpa jaringan, rootfs read-only,
  non-root, batas resource, timeout per eksekusi). Kernel dihentikan setelah idle
  (`KERNEL_IDLE_TTL_SECONDS`), saat batas kernel aktif tercapai (`KERNEL_MAX_ACTIVE`, yang paling
  lama idle lebih dulu), atau saat thread dihapus. Model diberi tahu saat memakai kernel baru.
  Workspace tetap sumber kebenaran. `run_shell` tetap sekali pakai.
- **FR-62** Rencana dan verifikasi. Tool harness `update_plan` menyimpan rencana yang dibuat dan
  direvisi model di state thread, dan rencana itu disisipkan ke system prompt setiap giliran. Agent
  yang mengaktifkannya menjalankan langkah verifikasi sebelum jawaban akhir: angka berasal dari
  output tool, metrik sesuai katalog, filter dan periode sesuai pertanyaan, dan keterbatasan data
  disebut. Verifikasi yang gagal mengembalikan run ke loop, yang tetap dibatasi FR-59.
- **FR-52** Project built-in "Data Analyst" yang disusun dari FR-51, FR-60, FR-61, FR-62, tool file
  (FR-47), dan playbook metode analisa sebagai skill generik (eksplorasi data, deskriptif, tren,
  perbandingan segmen, anomali, root cause berbasis hipotesis, cek kualitas data, pemilihan chart).
  Chart dibuat di kernel dan dibagikan sebagai artifact. Kualitas diukur dengan eval suite lintas
  dua dataset demo, dengan taksonomi pertanyaan: deskriptif, komparatif, tren, diagnostik, ambigu,
  jebakan kualitas data, dan tidak bisa dijawab. *Revisi dari FR-52 awal (semantic layer sebagai
  skill, satu skenario acceptance).*

### Fase 2: Scheduled Analytics (M9)

- **FR-53** Worker dan scheduler sebagai proses terpisah (service `worker` di `compose.yaml`). Job
  didefinisikan di file konfigurasi (`jobs.yaml`): jadwal cron, project, prompt, dan panjang jendela
  waktu. Setiap run memproses jendela setengah terbuka `[start, end)` yang sejajar jadwal (UTC).
  `job_runs` unik per `(job_id, window_start)`, sehingga tidak ada run dobel. Jendela yang
  terlewat dikejar saat worker start, dan run yang masih berjalan tidak ditumpuk.
- **FR-54** Laporan PDF dibuat secara deterministik di kode dari hasil analisa (narasi, tabel,
  chart). Hasil job terjadwal menjadi thread baru di project job, berisi message ringkasan dan
  artifact PDF.

### Fase 2: Knowledge (M10)

- **FR-55** Ingestion per Project. Dokumen yang di-upload (PDF, Markdown, DOCX, TXT) diproses worker:
  parse → chunk → embed (`EMBEDDING_MODEL`, endpoint OpenAI-compatible) → simpan di `pgvector`.
  Status per dokumen (`pending`, `ready`, `failed`). Dokumen yang sama (hash konten) tidak diproses
  ulang. Menghapus dokumen juga menghapus chunk-nya.
- **FR-56** Tool `search_knowledge(query)` mencari di knowledge Project yang aktif saja, dan
  jawabannya menyertakan sumber (dokumen + bagian). Kualitas retrieval diukur dengan eval set
  (FR-41).
- **FR-57** Tab Knowledge di halaman Project: upload, status, dan hapus dokumen.

### Fase 2: Interop (M11)

- **FR-58** Endpoint OpenAI-compatible: `GET /v1/models` (project dan agent sebagai model) dan
  `POST /v1/chat/completions` (stream dan non-stream). Stateless secara default. Reasoning dikirim
  sebagai `delta.reasoning_content`, dan artifact sebagai link di `content`. Tool call internal
  agent tidak diekspos sebagai `tool_calls`.

## 6. Non-Functional Requirements

| ID | Requirement | Ukuran |
|---|---|---|
| NFR-1 | Tanpa side effect saat import | `python -c "import agent_service.<modul>"` tidak membaca env, membuka koneksi, atau compile graph |
| NFR-2 | Type-safe | `pyrefly check` tanpa error |
| NFR-3 | Coverage | ≥ 80% baris |
| NFR-4 | Kompleksitas | Nesting ≤ 2, function/method ±≤ 40 baris (lihat AGENTS.md) |
| NFR-5 | Startup | Service siap < `STARTUP_TIMEOUT_SECONDS` (default 10 detik) tanpa jaringan |
| NFR-6 | Error contract | Error domain dan error tak terduga berbentuk `{"detail": str}` dengan status code yang tepat. Error validasi request (422) memakai format bawaan FastAPI: `detail` berupa list per field |
| NFR-7 | Observability | Logging terstruktur via `logging`. Setiap request punya `run_id` di log |
| NFR-8 | Reproducible | `uv.lock` di-commit. Docker image di-build dari lock file |
| NFR-9 | Isolasi data (Fase 2) | Thread, project, artifact, workspace, memory, dan knowledge milik user lain menghasilkan 404. Dites per resource |
| NFR-10 | Eksekusi kode (Fase 2) | Tidak ada `exec`/`eval`/subprocess untuk kode buatan model di proses service. Semua lewat `Sandbox` |
| NFR-11 | Frontend (Fase 2) | `tsc --noEmit`, ESLint, dan Vitest hijau. Tipe API hanya dari hasil generate (FR-35) |
| NFR-12 | Ukuran image (Fase 2) | Image `service` tidak berisi Streamlit. Ukuran image dicatat di PR F22 |
| NFR-13 | Analitik generik (M8) | Tidak ada nama domain di tool, prompt agent, skill, atau kode analitik. Eval agent data analyst dijalankan di minimal dua dataset dari domain berbeda |

## 7. Kontrak API

### 7.1 Endpoint

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/info` | – | `ServiceMetadata` |
| POST | `/{agent_id}/invoke` | `UserInput` | `ChatMessage` |
| POST | `/{agent_id}/stream` | `StreamInput` | `text/event-stream` |
| POST | `/{agent_id}/history` | `ChatHistoryInput` | `ChatHistory` |
| POST | `/auth/login` | `LoginRequest` | `TokenResponse` |
| GET | `/{agent_id}/threads` | query `limit` (1–100, default 20) | `UserThreads` |
| PATCH | `/{agent_id}/threads/{thread_id}` | `ThreadRenameInput` | `ThreadSummary` |
| DELETE | `/{agent_id}/threads/{thread_id}` | – | 204 |
| GET | `/skills`, `/skills/{scope}/{name}` | – | `SkillList` / `SkillDetail` |
| GET, POST | `/projects` | – / `ProjectCreate` | `ProjectList` / `Project` (201) |
| GET, PATCH, DELETE | `/projects/{project_id}` | – / `ProjectUpdate` / – | `Project` / `Project` / 204 |
| POST | `/projects/{project_id}/invoke`, `/stream`, `/history` | sama dengan route agent | sama dengan route agent |
| GET, PATCH, DELETE | `/projects/{project_id}/threads[/{thread_id}]` | sama dengan route agent | sama dengan route agent |
| GET | `/memories` | – | `MemoryList` |
| DELETE | `/memories/{memory_id}` | – | 204 |
| GET | `/runs/{run_id}/trace` | – | `RunTrace` |
| POST | `/artifacts` | multipart `file` | `ArtifactRef` (201) |
| GET | `/artifacts/{artifact_id}` | – | isi file (`attachment`) |
| DELETE | `/artifacts/{artifact_id}` | – | 204 |
| GET | `/health` | – | `{"status": "ok"}` |

Varian tanpa `{agent_id}` (`/invoke`, `/stream`, dan seterusnya) memakai agent default. Mulai F24,
semua endpoint kecuali `/health` dan `/auth/login` butuh `Authorization: Bearer <access_token>`,
dan pemilik thread diambil dari token (FR-33).

**Endpoint yang direncanakan (detail final ditetapkan di fitur masing-masing):**

| Method | Path | FR | Fitur |
|---|---|---|---|
| GET | `/jobs`, `/jobs/{job_id}/runs` | FR-53 | F41 |
| GET | `/datasources` | FR-51 | F39 |
| POST, GET, DELETE | `/projects/{project_id}/documents` | FR-55 | F43 |
| GET, POST | `/v1/models`, `/v1/chat/completions` | FR-58 | F46 |

### 7.2 Schema Utama

```text
LoginRequest    { username: str (huruf kecil, [a-z0-9._-], 3–32), password: str }
TokenResponse   { access_token: str, token_type: "bearer", expires_in: int, user_id: str,
                  username: str, role: "user"|"service" }
UserInput       { message: str, model?: str, thread_id?: str, agent_config?: dict,
                  artifact_ids?: list[str] }
StreamInput     UserInput + { stream_tokens: bool = true }
ChatMessage     { type: "human"|"ai"|"tool"|"custom", content: str, tool_calls: list,
                  tool_call_id?: str, run_id?: str, agent?: str, reasoning?: str,
                  truncated: bool, artifacts: list[ArtifactRef], response_metadata?: dict,
                  custom_data?: dict }
ArtifactRef     { id: str (UUID), name: str, mime_type: str, size: int }
ChatHistoryInput { thread_id: str }
ChatHistory     { messages: list[ChatMessage] }
ThreadSummary   { thread_id: str, agent_id: str, project_id?: str, title: str,
                  updated_at?: datetime }
ProjectCreate   { name: str, base_agent_id: str, description?: str, model?: str,
                  instructions?: str, skill_ids?: list["<scope>/<name>"],
                  settings?: ProjectSettings }
ProjectUpdate   ProjectCreate tanpa base_agent_id, semua opsional (PATCH)
ProjectSettings { max_tokens?: int, tool_approval: "never"|"always" = "never" }
SkillSummary    { id: "<scope>/<name>", name, description, scope, version, read_only,
                  resources: list[str] }
SkillDetail     SkillSummary + { body: str }
Project         ProjectCreate + { id, scope: "builtin"|"user", read_only, created_at,
                  updated_at }
ThreadRenameInput { title: str (1–TITLE_MAX_LENGTH karakter) }
AgentInfo       { key: str, description: str, config_schema: dict (JSON Schema) }
Memory          { id: str, text: str, created_at: datetime, updated_at: datetime }
RunTrace        { run_id, thread_id, agent_id, project_id?, status, started_at, ended_at,
                  duration_ms, input_tokens?, output_tokens?, error?, spans: list[TraceSpan] }
TraceSpan       { kind: "run"|"model"|"tool", name, status: "ok"|"error"|"interrupted",
                  started_at, ended_at, duration_ms, input_tokens?, output_tokens?, error? }
```

`agent_config` tidak boleh berisi key reservasi `thread_id`, `user_id`, atau `model` (422). Selain
itu, isinya harus lolos `config_schema` milik agent tujuan (FR-27).

### 7.3 Format SSE

Setiap frame berupa `data: <json>\n\n`:

```text
data: {"type": "reasoning", "content": "Pertama, ..."}   (FR-29, mulai F19)
data: {"type": "token",   "content": "Hal"}
data: {"type": "message", "content": { ...ChatMessage... }}
data: {"type": "error",   "content": "pesan error"}
data: [DONE]
```

Stream selalu diakhiri `[DONE]`, termasuk ketika terjadi error. Urutan per run: frame `token`
(jika `stream_tokens`), lalu frame `message` untuk setiap message baru dari node (jawaban AI, tool
call, hasil tool, pertanyaan interrupt, event custom), lalu `[DONE]`. Input human tidak di-echo.
Node yang LLM-nya diberi tag `skip_stream` tidak menghasilkan frame `token`.

## 8. Konfigurasi (env var)

| Variabel | Default | Keterangan |
|---|---|---|
| `LLM_BASE_URL` | – | Endpoint OpenAI-compatible |
| `LLM_API_KEY` | – | API key |
| `DEFAULT_MODEL` | – | Model default |
| `AVAILABLE_MODELS` | `DEFAULT_MODEL` | Allowlist, dipisah koma |
| `USE_FAKE_MODEL` | `false` | Pakai FakeModel (dev/test) |
| `LLM_MAX_TOKENS` | `8192` | Batas token jawaban per giliran, termasuk reasoning pada provider yang menghitungnya bersama (FR-30) |
| `LLM_MAX_TOKENS_PARAM` | `max_tokens` | Nama parameter batas token di request. `max_completion_tokens` untuk model reasoning OpenAI. Ollama hanya membaca `max_tokens` |
| `DATABASE_URL` | `postgresql://agent:agent@127.0.0.1:5432/agent_service` | Koneksi Postgres (FR-32). Menggantikan `SQLITE_DB_PATH` mulai F23 |
| `JWT_SECRET` | – (wajib) | Kunci HS256 access token, minimal 32 karakter (FR-33). Menggantikan `AUTH_SECRET` mulai F24 |
| `JWT_TTL_SECONDS` | `43200` | Umur access token (12 jam), tanpa refresh token |
| `CORS_ORIGINS` | – | Origin browser yang diizinkan, dipisah koma (FR-34) |
| `CONTEXT_MAX_TOKENS` | `16000` | Anggaran token riwayat yang dikirim ke model, minimum 1000 (FR-39) |
| `ARTIFACT_DIR` | `data/artifacts` | Folder isi file artifact (FR-46) |
| `ARTIFACT_MAX_BYTES` | `26214400` (25 MB) | Batas ukuran artifact dan file workspace (FR-46, FR-47) |
| `TOOL_OUTPUT_MAX_TOKENS` | `4000` | Batas output tool sebelum dipindah ke workspace (FR-48) |
| `SANDBOX_URL`, `SANDBOX_TOKEN` | – | URL dan token bersama `sandbox-runner`. Kosong = tanpa tool eksekusi (FR-49) |
| `SANDBOX_TIMEOUT_SECONDS` | `60` | Batas waktu satu eksekusi kode, maksimum 600 |
| `AGENT_RECURSION_LIMIT` | `50` | Batas langkah graph per run, minimum 4 (FR-59) |
| `TOOL_MAX_CONSECUTIVE_ERRORS` | `3` | Kegagalan beruntun per tool di satu giliran sebelum tool dihentikan (FR-59) |
| `SANDBOX_IMAGE` | image sandbox compose | Dibaca `sandbox-runner`, bukan service API |
| `FIRECRAWL_API_KEY` | – | Key Firecrawl untuk tool `web_search`. Kosong = tool menjawab "not configured", agent tetap berjalan |
| `HOST` / `PORT` | `0.0.0.0` / `8080` | Bind address service |
| `LOG_LEVEL` | `INFO` | Level logging |
| `AGENT_URL` | `http://localhost:8080` | Dipakai UI/client/eval |
| `EVAL_USERNAME`, `EVAL_PASSWORD`, `EVAL_TIMEOUT_SECONDS` | –, –, `300` | Akun dan batas waktu runner eval (FR-41) |

`SQLITE_DB_PATH` (digantikan `DATABASE_URL` di F23) dan `AUTH_SECRET` (digantikan `JWT_SECRET` di
F24) sudah dihapus.

**Env var yang direncanakan:**

| Variabel | Fitur | Keterangan |
|---|---|---|
| `DATA_SOURCES_FILE` | F39 | Registry data source read-only. DSN setiap data source dibaca dari env yang namanya disebut di file. Menggantikan rencana `DATA_SOURCE_URL` |
| `SQL_MAX_ROWS` | F39 | Batas baris hasil `run_sql` |
| `KERNEL_IDLE_TTL_SECONDS`, `KERNEL_MAX_ACTIVE` | F49 | Umur kernel idle dan jumlah kernel aktif (dibaca `sandbox-runner`) |
| `JOBS_FILE` | F41 | Lokasi definisi job terjadwal |
| `EMBEDDING_MODEL` | F43 | Model embedding OpenAI-compatible |

## 9. Out of Scope v1 → Future

| Fitur | Catatan |
|---|---|
| Provider LLM lain (Anthropic, Google, Bedrock, Ollama) | Tambah strategy di `ModelFactory` |
| Postgres checkpointer + store | **Masuk Fase 2:** F23, F30 |
| RAG (Chroma) | **Masuk Fase 2** dengan `pgvector`, bukan Chroma: F43–F45 |
| Long-term memory (Store) | **Masuk Fase 2:** F30 |
| MCP agent | Memakai `async load()` dari `BaseAgent` |
| Tracing (Langfuse/LangSmith), feedback | **Tracing masuk Fase 2:** F31. Feedback tetap Future |
| AG-UI | Adapter opsional (backlog B4) |
| Voice | Tidak direncanakan |
| Skill dan job lewat UI, SSO, sandbox production | Backlog B1, B2, B6, B5 (lihat ROADMAP) |

## 10. Milestone

Rincian fitur per milestone, urutan eksekusi, dan rencana commit ada di
[docs/ROADMAP.md](docs/ROADMAP.md).

| Milestone | Isi | Kriteria selesai |
|---|---|---|
| **M1: Core + Service** | `Settings`, `ModelFactory`, `CheckpointerProvider`, `BaseAgent`, `AgentRegistry`, agent `chatbot`, semua endpoint FR-5–FR-16 | Test endpoint hijau dengan FakeModel |
| **M2: Client + UI** | `AgentClient`, Streamlit app FR-20–FR-24 | Chat end-to-end via Docker Compose |
| **M3: Agent tambahan** | Reasoning terlihat (FR-29), `research-assistant`, `interrupt-agent`, `supervisor` | Test per agent + streaming subgraph + frame `reasoning` |
| **M4: Foundation** | FR-30–FR-35 | Stack compose dengan Postgres + login JWT berjalan, kontrak API dicek CI |
| **M5: Harness Core** | FR-36–FR-41 | Project built-in memakai skill lewat `load_skill`, eval berjalan |
| **M6: Frontend** | FR-42–FR-45 | Demo chat di browser dengan Projects dan reasoning |
| **M7: Files & Execution** | FR-46–FR-50 | Agent menulis file dan menjalankan Python di sandbox, hasilnya tampil di panel artifact |
| **M8: Analytics Core** | FR-51, FR-52, FR-59–FR-62 | Agent analisa data dari primitif generik lolos ambang eval di dua dataset demo, termasuk pertanyaan diagnostik |
| **M9: Scheduled Analytics** | FR-53, FR-54 | Job terjadwal menghasilkan thread berisi laporan PDF yang lolos verifikasi |
| **M10: Knowledge** | FR-55–FR-57 | Upload dokumen → jawaban dengan sumber |
| **M11: Interop** | FR-58 | SDK `openai` bisa chat dengan Project |

## 11. Open Questions

1. ~~Apakah `/threads` perlu fitur hapus/rename thread di v1?~~ **Terjawab (2026-11-01):** ya,
   lihat FR-25 dan FR-26.
2. ~~Web search memakai DuckDuckGo (tanpa key) atau provider lain?~~ **Terjawab (2026-11-01):**
   DuckDuckGo. **Diganti (2026-11-12):** Firecrawl Search API (`FIRECRAWL_API_KEY`), karena
   DuckDuckGo tidak stabil (F20).
3. ~~Perlukah `agent_config` divalidasi dengan schema per agent (Pydantic model milik agent)?~~
   **Terjawab (2026-11-01):** ya, lihat FR-27.
4. ~~Nama package final: `agent_service` atau yang lain?~~ **Terjawab (2026-11-01):**
   `agent_service`.
5. ~~Apakah reasoning model (FR-29) disimpan di riwayat thread dan ditampilkan lagi saat
   thread dibuka ulang, atau hanya tampil selama stream berlangsung?~~ **Terjawab (2026-11-12):**
   disimpan. `ChatMessage.reasoning` dikembalikan oleh `/invoke` dan `/history`, dan UI
   menampilkannya tertutup saat thread dibuka ulang. Reasoning tidak dikirim balik ke model.

**Fase 2 (dijawab di Langkah 1 fitur terkait):**

6. Sumber data analisa: apakah sudah ada read replica atau user database read-only? Apakah data
   perlu di-mask (PII) sebelum dikirim ke LLM yang bukan lokal? (F39)
7. ~~Backend tracing: Langfuse self-hosted, OpenTelemetry, atau tabel trace sendiri di Postgres?
   (F31)~~ **Terjawab (2026-11-17):** tabel `run_traces` di Postgres, dibaca lewat
   `GET /runs/{run_id}/trace`. Langfuse/OTel bisa ditambahkan kemudian sebagai exporter.
8. ~~Bentuk route chat berbasis Project: `project_id` di body route lama, atau route baru
   `/projects/{project_id}/stream`? (F26)~~ **Terjawab (2026-11-15):** route baru
   `/projects/{project_id}/invoke|stream|history|threads`. Route `/{agent_id}/...` tetap untuk
   chat tanpa project.
9. Library PDF: `fpdf2`/`reportlab` (pure Python) atau WeasyPrint (HTML → PDF, butuh library
   sistem)? (F42)
10. Parser dokumen untuk ingestion: cukup pypdf + python-docx, atau perlu parser tabel/scan
    (Docling)? (F43)
11. Profiling tabel besar di `profile_table`: sampling, statistik `pg_stats`, atau batas ukuran
    tabel? (F39)
12. Implementasi kernel per thread: Jupyter kernel lewat `jupyter_client`, atau REPL server kecil
    buatan sendiri di image sandbox? (F49)
