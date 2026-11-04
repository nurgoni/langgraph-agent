# PRD: LangGraph Agent Service (Rewrite)

| | |
|---|---|
| Status | Draft |
| Versi dokumen | 0.1 |
| Tanggal | 2026-11-01 |
| Referensi | `agent-service-toolkit/` (kode asli) |

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

## 3. Non-Goals (v1)

- Banyak provider LLM sekaligus. v1 hanya memakai endpoint OpenAI-compatible + FakeModel.
- Backend persistence selain SQLite.
- Voice (STT/TTS), AG-UI protocol, Langfuse/LangSmith tracing dan feedback.
- Safeguard/prompt-injection classifier.
- Multi-tenant auth (user management, OAuth). v1 hanya memakai shared bearer token.
- Deployment cloud. v1 cukup Docker Compose lokal.

## 4. Persona

| Persona | Kebutuhan |
|---|---|
| **Agent developer** | Menulis agent LangGraph baru dan langsung bisa mencobanya lewat API/UI tanpa memahami internal service. |
| **Integrator** | Memanggil agent dari aplikasi lain lewat HTTP atau `AgentClient`. |
| **End user** | Chat dengan agent di browser, melihat jawaban mengalir, melanjutkan percakapan lama. |

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
- **FR-7** `POST /{agent_id}/stream` mengalirkan event SSE (lihat §7.2).
- **FR-8** `POST /{agent_id}/history` mengembalikan riwayat message satu thread. Request wajib
  menyertakan `user_id`. Thread milik user lain diperlakukan sebagai tidak ada (404), sama dengan
  FR-25/26.
- **FR-9** `GET /{agent_id}/threads?user_id=...` mengembalikan daftar thread milik user (judul,
  waktu update), dengan paginasi.
- **FR-25** `PATCH /{agent_id}/threads/{thread_id}` mengganti judul thread (`{"user_id", "title"}`).
  Judul custom disimpan terpisah dari checkpoint dan menimpa judul otomatis. Hanya pemilik thread
  yang boleh mengganti judul. Thread milik user lain diperlakukan sebagai tidak ada (404).
- **FR-26** `DELETE /{agent_id}/threads/{thread_id}?user_id=...` menghapus thread: semua checkpoint
  (`checkpointer.adelete_thread`) dan metadata judulnya. Aturan kepemilikan sama dengan FR-25.
  Response 204.
- **FR-10** `GET /health` selalu tanpa auth.
- **FR-11** Jika `AUTH_SECRET` diset, semua endpoint kecuali `/health` membutuhkan
  `Authorization: Bearer <AUTH_SECRET>`.
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
  lifespan, ditutup saat shutdown.

### Client

- **FR-17** `AgentClient` menyediakan method sync dan async: `invoke`, `stream`, `get_history`,
  `get_threads`, `get_info`.
- **FR-18** Error HTTP dibungkus menjadi `AgentClientError` dengan status code dan pesan.
- **FR-19** Tidak ada network call di konstruktor `AgentClient`. `/info` diambil secara lazy.

### UI (Streamlit)

- **FR-20** Chat dengan streaming token, menampilkan tool call sebagai status box yang bisa
  di-expand.
- **FR-21** Sidebar: tombol chat baru, daftar thread sebelumnya (dengan aksi rename dan hapus),
  pemilih agent dan model, toggle streaming.
- **FR-22** `thread_id` dan `agent_id` disimpan di URL query param sehingga percakapan bisa dibuka
  ulang.
- **FR-23** Menampilkan handoff sub-agent (supervisor) secara bertingkat.
- **FR-24** Saat agent meminta input (interrupt), pertanyaannya ditampilkan sebagai pesan AI biasa.

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

## 7. Kontrak API

### 7.1 Endpoint

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/info` | – | `ServiceMetadata` |
| POST | `/{agent_id}/invoke` | `UserInput` | `ChatMessage` |
| POST | `/{agent_id}/stream` | `StreamInput` | `text/event-stream` |
| POST | `/{agent_id}/history` | `ChatHistoryInput` | `ChatHistory` |
| GET | `/{agent_id}/threads` | query `user_id`, `limit` (1–100, default 20) | `UserThreads` |
| PATCH | `/{agent_id}/threads/{thread_id}` | `ThreadRenameInput` | `ThreadSummary` |
| DELETE | `/{agent_id}/threads/{thread_id}` | query `user_id` | 204 |
| GET | `/health` | – | `{"status": "ok"}` |

Varian tanpa `{agent_id}` (`/invoke`, `/stream`, dan seterusnya) memakai agent default.

### 7.2 Schema Utama

```text
UserInput       { message: str, model?: str, thread_id?: str, user_id?: str, agent_config?: dict }
StreamInput     UserInput + { stream_tokens: bool = true }
ChatMessage     { type: "human"|"ai"|"tool"|"custom", content: str, tool_calls: list,
                  tool_call_id?: str, run_id?: str, custom_data?: dict }
ChatHistoryInput { thread_id: str, user_id: str }
ChatHistory     { messages: list[ChatMessage] }
ThreadSummary   { thread_id: str, agent_id: str, title: str, updated_at?: datetime }
ThreadRenameInput { user_id: str, title: str (1–TITLE_MAX_LENGTH karakter) }
AgentInfo       { key: str, description: str, config_schema: dict (JSON Schema) }
```

`agent_config` tidak boleh berisi key reservasi `thread_id`, `user_id`, atau `model` (422). Selain
itu, isinya harus lolos `config_schema` milik agent tujuan (FR-27).

### 7.3 Format SSE

Setiap frame berupa `data: <json>\n\n`:

```text
data: {"type": "token",   "content": "Hal"}
data: {"type": "message", "content": { ...ChatMessage... }}
data: {"type": "error",   "content": "pesan error"}
data: [DONE]
```

Stream selalu diakhiri `[DONE]`, termasuk ketika terjadi error.

## 8. Konfigurasi (env var v1)

| Variabel | Default | Keterangan |
|---|---|---|
| `LLM_BASE_URL` | – | Endpoint OpenAI-compatible |
| `LLM_API_KEY` | – | API key |
| `DEFAULT_MODEL` | – | Model default |
| `AVAILABLE_MODELS` | `DEFAULT_MODEL` | Allowlist, dipisah koma |
| `USE_FAKE_MODEL` | `false` | Pakai FakeModel (dev/test) |
| `SQLITE_DB_PATH` | `checkpoints.db` | Lokasi DB checkpointer |
| `AUTH_SECRET` | – | Bearer token. Kosong = tanpa auth |
| `HOST` / `PORT` | `0.0.0.0` / `8080` | Bind address service |
| `LOG_LEVEL` | `INFO` | Level logging |
| `AGENT_URL` | `http://localhost:8080` | Dipakai UI/client |

## 9. Out of Scope v1 → Future

| Fitur | Catatan |
|---|---|
| Provider LLM lain (Anthropic, Google, Bedrock, Ollama) | Tambah strategy di `ModelFactory` |
| Postgres checkpointer + store | Tambah implementasi `CheckpointerProvider` |
| RAG (Chroma) | Instance `ToolCallingAgent` + tool retriever yang dibuat sekali |
| Long-term memory (Store) | Dibutuhkan jika interrupt-agent perlu mengingat lintas thread |
| MCP agent | Memakai `async load()` dari `BaseAgent` |
| Tracing (Langfuse/LangSmith), feedback | Callback opsional |
| Voice, AG-UI | Tidak direncanakan |

## 10. Milestone

Rincian fitur per milestone, urutan eksekusi, dan rencana commit ada di
[docs/ROADMAP.md](docs/ROADMAP.md).

| Milestone | Isi | Kriteria selesai |
|---|---|---|
| **M1: Core + Service** | `Settings`, `ModelFactory`, `CheckpointerProvider`, `BaseAgent`, `AgentRegistry`, agent `chatbot`, semua endpoint FR-5–FR-16 | Test endpoint hijau dengan FakeModel |
| **M2: Client + UI** | `AgentClient`, Streamlit app FR-20–FR-24 | Chat end-to-end via Docker Compose |
| **M3: Agent tambahan** | `research-assistant`, `interrupt-agent`, `supervisor` | Test per agent + streaming subgraph |

## 11. Open Questions

1. ~~Apakah `/threads` perlu fitur hapus/rename thread di v1?~~ **Terjawab (2026-11-01):** ya,
   lihat FR-25 dan FR-26.
2. ~~Web search memakai DuckDuckGo (tanpa key) atau provider lain?~~ **Terjawab (2026-11-01):**
   DuckDuckGo.
3. ~~Perlukah `agent_config` divalidasi dengan schema per agent (Pydantic model milik agent)?~~
   **Terjawab (2026-11-01):** ya, lihat FR-27.
4. ~~Nama package final: `agent_service` atau yang lain?~~ **Terjawab (2026-11-01):**
   `agent_service`.
