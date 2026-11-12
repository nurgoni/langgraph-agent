# Changelog

Semua perubahan penting dicatat di file ini. Format mengikuti
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), dan versi mengikuti
[Semantic Versioning](https://semver.org/). Proses rilis ada di [CONTRIBUTING.md](CONTRIBUTING.md#release).

## [Unreleased]

### Added

- Reasoning model terlihat: field reasoning dari provider OpenAI-compatible (`reasoning`/
  `reasoning_content`) diteruskan sebagai frame SSE `reasoning` sebelum token jawaban, disimpan
  di `ChatMessage.reasoning`, dan ditampilkan di blok "Thinking" UI yang bisa dibuka-tutup
  (F19).
- Agent `research-assistant`: `ToolCallingAgent` generik dengan tool web search DuckDuckGo (tanpa
  API key) dan kalkulator numexpr. Error tool dikembalikan ke model agar bisa dicoba ulang (F15).

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

[Unreleased]: https://github.com/nurgoni/langgraph-boilerplate-agent/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/nurgoni/langgraph-boilerplate-agent/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/nurgoni/langgraph-boilerplate-agent/releases/tag/v0.1.0
