# Project Memory

Memori kerja untuk coding agent dan kontributor. Baca sebelum mulai bekerja dan perbarui setelah
ada keputusan penting (lihat Definition of Done di [AGENTS.md](../AGENTS.md)).

**Aturan file ini:**

- Entri Decision Log bersifat append-only, dan entri terbaru ditaruh **paling atas**.
- Entri yang salah tidak dihapus. Tambahkan entri baru yang membatalkannya ("Supersedes: ...").
- Jaga file tetap ringkas (< ~300 baris) karena dimuat otomatis di setiap sesi. Keputusan besar yang
  sudah stabil dipindah ke `docs/adr/`.
- Tanggal ditulis absolut (YYYY-MM-DD).

## Status Saat Ini

- **Fase:** M0 selesai (F00). Repo git, tooling, dan CI siap. Belum ada kode fitur.
- **Berikutnya:** F01 (core settings) di [docs/ROADMAP.md](../docs/ROADMAP.md#f01-core-settings).
- **Repo:** belum ada remote. PR dan CI GitHub baru berjalan setelah remote ditambahkan. Sampai
  saat itu, merge ke `develop` dilakukan sebagai squash merge lokal setelah cek lokal hijau.
- **Terakhir diperbarui:** 2026-11-01

## Decision Log

### 2026-11-01: Konvensi tooling dari F00

- **Keputusan:**
  - Dependency runtime ditambahkan oleh fitur yang pertama kali membutuhkannya (`dependencies = []`
    di F00).
  - Tool dev di-pin sampai minor (`ruff ~=0.17.1`, `pyrefly ~=1.4.0`), karena rilis minor bisa
    mengubah hasil lint/format.
  - Hook pre-commit untuk ruff/pyrefly memakai `uv run` (hook lokal), sehingga versinya sama dengan
    `uv.lock`.
  - pytest berjalan di stage `pre-push`.
  - uv di CI di-pin ke versi yang menulis `uv.lock` (0.12.18).
  - `exclude-newer` memakai tanggal absolut dan dimajukan setiap kali dependency di-refresh.
  - `.gitattributes` memaksa line ending LF, karena git di mesin Windows ini memakai `autocrlf`.
  - Git author di repo ini: `user.name = nurgoni` (config lokal).
- **Alasan:** toolkit lama mengalami drift versi antara hook dan dev dependency (ruff v0.11.9 vs
  0.15). Pytest mengembalikan exit code 5 kalau tidak ada test, jadi setiap commit minimal punya
  smoke test.

### 2026-11-01: Thread rename/delete + validasi `agent_config` per agent masuk v1

- **Keputusan:** tambah FR-25 (rename), FR-26 (delete), dan FR-27 (`config_schema` per agent).
  Rename/delete dikerjakan sebagai fitur baru **F18** (M1). Validasi config dimasukkan ke
  F04/F05/F06/F07. UI-nya masuk F13.
- **Alasan:** jawaban user untuk open question PRD §11 no. 1 dan 3.
- **Catatan desain:** judul custom disimpan di tabel `thread_metadata` (SQLite yang sama), karena
  metadata checkpoint LangGraph tidak dirancang untuk diubah. Akses ke thread milik user lain
  menghasilkan 404 supaya keberadaan thread tidak bocor.

### 2026-11-01: Git lifecycle

- **Keputusan:** Git Flow ringan (`main` + `develop`), branch `feature/Fxx-<slug>`, squash merge
  ke develop, release ke main dengan `--no-ff` + tag annotated, lalu back-merge. Commit message
  memakai Conventional Commits dalam bahasa Inggris, scope = layer (`memory-md` untuk file ini).
- **Alasan:** pilihan user. Squash menjaga develop tetap 1 commit per fitur. Release sengaja
  tidak di-squash supaya histori main dan develop tetap terhubung. Bahasa Inggris dipilih agar
  kompatibel dengan tooling changelog.
- **Detail:** [CONTRIBUTING.md](../CONTRIBUTING.md).

### 2026-11-01: Package `agent_service`, web search DuckDuckGo

- **Keputusan:** nama package `agent_service`. Tool web search memakai DuckDuckGo.
- **Alasan:** pilihan user. DuckDuckGo tidak butuh API key, sama seperti toolkit lama.

### 2026-11-01: Konverter LangChain → ChatMessage ada di `service/`, bukan `schema/`

- **Keputusan:** `langchain_to_chat_message` diletakkan di `service/converters.py` (F07).
- **Alasan:** AGENTS.md melarang `schema/` bergantung pada langchain, supaya client dan UI bisa
  memakai schema tanpa membawa dependency agent.

### 2026-11-01: Lokasi memory.md di `.agents/`

- **Keputusan:** memory disimpan di `.agents/memory.md`, bukan di `.claude/` atau `docs/`.
- **Alasan:** `.claude/` khusus konfigurasi Claude Code, sedangkan `docs/` untuk dokumen manusia
  yang stabil. `.agents/` netral terhadap tool dan berpasangan dengan `AGENTS.md`. Karena folder
  tersembunyi dilewati glob/ripgrep secara default, file ini ditautkan eksplisit dari AGENTS.md dan
  di-import oleh CLAUDE.md.

### 2026-11-01: Class sebagai default, function sebagai pengecualian

- **Keputusan:** komponen dengan state, dependency, atau lifecycle ditulis sebagai class. Function
  hanya untuk node LangGraph murni, `@tool`, transformasi murni, dependency FastAPI/entrypoint,
  dan fixture pytest.
- **Alasan:** preferensi user. Class juga membuat dependency eksplisit dan menghilangkan global
  state, yang merupakan masalah utama kode lama. Detail ada di AGENTS.md § Class vs Function.

### 2026-11-01: Scope v1 dipersempit

- **Keputusan:** v1 berisi FastAPI + SSE, AgentClient + Streamlit, dan multi-agent registry. Hanya
  satu jalur LLM (OpenAI-compatible + FakeModel) dan hanya SQLite.
- **Alasan:** user tidak memilih multi-provider/multi-DB. Kode lama punya 12 provider dan 3 DB,
  sehingga `settings.py` dan `llm.py` membengkak.
- **Dibuang dari v1:** voice, AG-UI, Langfuse, LangSmith feedback, safeguard Groq, Mongo, Postgres.

### 2026-11-01: Research & RAG assistant digabung

- **Keputusan:** satu class `ToolCallingAgent` yang dikonfigurasi lewat daftar tools.
- **Alasan:** `research_assistant.py` dan `rag_assistant.py` di kode lama ~90% identik.

### 2026-11-01: Bahasa & lokasi dokumen

- **Keputusan:** dokumen ditulis dalam Bahasa Indonesia (istilah teknis tetap Inggris).
  AGENTS.md, PRD.md, dan README.md diletakkan di root `langgraph-boilerplate/`.
- **Alasan:** pilihan user. `agent-service-toolkit/` dibiarkan utuh sebagai referensi read-only.

## Pelajaran dari Kode Lama

Path relatif terhadap `agent-service-toolkit/src/`. Gunakan sebagai daftar "jangan diulang" saat
melakukan port.

| Masalah | Lokasi | Solusi di rewrite |
|---|---|---|
| `Settings()` dibuat saat import, raise jika tanpa key | `core/settings.py:262` | Dibuat di lifespan/factory |
| Model dibuat di level modul, pilihan model user diabaikan | `agents/langgraph_supervisor_agent.py:8` | `BaseAgent.build(model, ...)` per request/model |
| `current_date` dihitung saat import (basi) | `agents/research_assistant.py:39` | Dihitung di dalam node |
| Registry berupa dict global | `agents/agents.py:34` | `AgentRegistry` instance di `app.state` |
| Checkpointer ditempel ke graph setelah compile | `service/service.py:112-114` | `graph.compile(checkpointer=...)` |
| `message_generator` ±110 baris, nesting 6+ | `service/service.py:243-353` | `StreamService` dengan method kecil per jenis event |
| Deteksi sub-agent lewat string nama node | `service/service.py:282` | Tag/metadata eksplisit |
| Agent tidak dikenal → `KeyError` → 500 | `service/service.py:217` | `AgentNotFoundError` → 404 |
| Mutable default `data: dict = {}` | `agents/bg_task_agent/task.py:32` | `None` / `default_factory` |
| Chroma dibangun ulang tiap tool call, path hard-coded | `agents/tools.py:60-68` | Dibuat sekali, path dari Settings |
| `match` provider diulang 12 kali | `core/settings.py:178-251` | Satu provider di v1, strategy map di Future |
| Request client dibangun 4 kali | `client/client.py` | Satu method privat `_build_payload` |
| `except Exception` di ±22 lokasi | `service/`, `agents/`, `voice/` | Exception spesifik, catch-all hanya di batas SSE |
| Magic number (`timeout=60`, `ttl=600`, `k=5`, `remaining_steps < 2`) | `core/llm.py:97`, `streamlit_app.py:56`, `agents/research_assistant.py:75` | Konstanta bernama |
| UI widget (`TaskDataStatus`) di package schema | `schema/task_data.py` | Dipindah ke `ui/` |
| `print()` sebagai log | `agents/safeguard.py`, `agents/command_agent.py` | `logging` |
| Streamlit `main()` ±300 baris, `draw_messages` nesting ±7 | `streamlit_app.py:67-525` | Class view per komponen |

## Pola yang Dipertahankan

- **Konstanta bernama** di `service/threads.py:21-32` (`MAX_THREAD_HEADS`, `TITLE_MAX_LENGTH`, dan
  lainnya). Ini contoh yang baik.
- **Kontrak SSE** `{"type": "message"|"token"|"error"}` + `[DONE]`.
- **Lazy loading agent** (`agents/lazy_agent.py`) → menjadi `BaseAgent.load()`.
- **Bentuk schema Pydantic** di `schema/schema.py` (`UserInput`, `ChatMessage`, dan lainnya).
- **Resume interrupt** dengan `Command(resume=...)` jika thread punya pending interrupt.
- **Filter thread per user** dengan pengecekan ulang metadata agar tidak bocor lintas user
  (`service/threads.py`).
- **Toolchain** uv + ruff + pyrefly + pytest, dan `exclude-newer` di uv untuk supply-chain safety.

## Pertanyaan Terbuka

Sinkron dengan [PRD.md §11](../PRD.md#11-open-questions). Saat ini tidak ada pertanyaan terbuka.

## TODO Berikutnya

- [ ] Tambahkan remote GitHub, push `main` + `develop`, set `develop` sebagai default branch, dan
      aktifkan branch protection (CONTRIBUTING.md § Setup Awal Repo).
- [ ] F01: core settings.
