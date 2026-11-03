# Changelog

Semua perubahan penting dicatat di file ini. Format mengikuti
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), dan versi mengikuti
[Semantic Versioning](https://semver.org/). Proses rilis ada di [CONTRIBUTING.md](CONTRIBUTING.md#release).

## [Unreleased]

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
