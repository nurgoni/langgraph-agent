# Decision Log F26–F31 (arsip)

Dipindah utuh dari `.agents/memory.md` pada 2026-11-17 (skill `memory-maintenance`), setelah
v0.5.0 (M5 Harness Core) dirilis. Entri terbaru di atas. Pelajaran yang masih berlaku
diringkas di memory.md § Pelajaran Lintas Fitur.

### 2026-11-17: Trace dan eval dari F31

- **Keputusan user:** trace di tabel Postgres `run_traces` (PRD §11 no. 7 terjawab), dibaca lewat
  `GET /runs/{run_id}/trace`. LLM judge ditunda.
- **Keputusan desain:**
  - `service/tracing.py` `RunTraceCollector` (AsyncCallbackHandler) per run, dipasang lewat
    `RunInput.with_callbacks`. Span `run`/`model`/`tool` tanpa hierarki dan tanpa konten, ditulis
    sekali di akhir run. `SQLAlchemyError` saat menulis hanya di-log.
  - `GraphBubbleUp` (interrupt) → status `interrupted`, bukan `error`.
  - `memory/traces.py` `RunTraceRepository`; trace milik user lain → `RunTraceNotFoundError` (404).
  - `ModelFactory` `stream_usage=True`: token dari `usage_metadata`.
  - `evals/` hanya meng-import `client/` + `schema/` (test layering), punya `EvalSettings` sendiri
    (seperti UI) dan extra `evals`. Entrypoint `run_evals`, exit 0/1/2. Laporan di
    `eval-reports/` (gitignore).
  - Skill yang dimuat dibaca dari argumen `load_skill` di `/history`; latensi/token dari trace.
- **Hasil ukur:** `qwen3.5:9b` dengan `evals/skills.yaml`: 2/3 lolos. Meeting notes memuat skill
  (16 dtk, 1928/274 token), pertanyaan umum tanpa skill (1,4 dtk). Briefing solar/angin **tidak**
  memuat `research-report` (temuan perilaku model, bukan bug). Ollama mengirim usage saat
  streaming dengan `stream_usage=True`.
- **Pelajaran:**
  - Nama model di callback: `metadata["ls_model_name"]` (ChatOpenAI), kwarg `name` bisa `None`,
    jadi fallback ke `serialized["name"]` (FakeModel).
  - Schema login client memvalidasi username sebelum request, jadi CLI harus menangkap
    `ValidationError` selain `AgentClientError`.
  - Jangan melakukan mutation check di `src/` selama test e2e Docker berjalan: build image
    menyalin `src/` dan mutasi bisa ikut masuk.
  - Fixture di `tests/<folder>/conftest.py` tidak terlihat dari test di folder lain.

### 2026-11-17: Long-term memory dari F30

- **Keputusan user:** persetujuan `save_memory` lewat balasan teks pada interrupt (tanpa field API).
  Prompt berisi memory terbaru (≤ 20), `search_memory` mencari kata kunci. Memory hanya untuk
  `chatbot` dan `research-assistant`.
- **Keputusan desain:**
  - `memory/store.py` `StoreProvider` + `memory/pool.py` (pool bersama checkpointer).
    `memory/user_memories.py` `UserMemoryRepository`: namespace `("users", user_id, "memories")`,
    ID uuid5 dari teks, maksimal 200 memory × 500 karakter, `delete` → `MemoryNotFoundError` (404).
  - `BaseAgent.build(model, checkpointer, store=None)`, `AgentRegistry(..., store)`. Tool dibuat
    per graph (closure atas repository), bukan `get_store()`.
  - `ContextBuilder` tidak lagi punya slot `memory`; `system_message(config, summary, memories)`.
  - `is_approval`: kata pertama harus kata setuju, dan semua kata harus kata setuju/pengisi.
  - `USER_ID_CONFIG_KEY` di `core/constants.py`. Revisi Alembic `0004` tanpa perubahan skema
    sebagai penanda tabel store.
- **Pelajaran:**
  - `interrupt()` di dalam tool bekerja di `ToolNode`, tetapi saat run dilanjutkan **semua** tool
    call di giliran itu dijalankan ulang, termasuk yang sudah disetujui. Efek samping tool harus
    idempoten. Dua interrupt dalam satu giliran ditanyakan bergantian, dan jawaban dipasangkan
    berurutan.
  - `InMemoryStore.asearch` mengembalikan urutan sisip dan memotong `limit` sebelum urutan apa
    pun, sedangkan `AsyncPostgresStore` mengurutkan `updated_at` menurun. Urutkan di repository.
  - Timestamp dua penyimpanan beruntun di Windows bisa sama persis. Test urutan butuh jeda kecil.
  - Prefix namespace store dicocokkan per elemen: `("users", "u")` tidak cocok dengan `u1`.
  - Fixture test mengosongkan semua tabel kecuali tabel migrasi. Tabel migrasi baru
    (`store_migrations`) harus masuk `KEPT_TABLES`.
  - Mengubah signature method abstract (`build`) mewajibkan semua agent tiruan di test ikut diubah,
    karena pyrefly menandai override yang kurang parameter.

### 2026-11-17: Context policy dari F29

- **Keputusan user:** `CONTEXT_MAX_TOKENS` default 16.000. Peringkasan bertahap: saat anggaran
  terlampaui, unit lama diringkas sampai riwayat langsung tinggal ±50% anggaran.
- **Keputusan desain:**
  - `harness/context_policy.py`: `message_units` (AI + `ToolMessage`-nya = satu unit),
    `ContextPolicy.prepare(model, messages, summary, summarized_through) -> ContextWindow`.
    Anggaran = riwayat + ringkasan. Ringkasan ≤ min(4000 karakter, ¼ anggaran).
  - State agent (`ToolCallingState`, `SupervisorState`): `summary` dan `summarized_through`
    (`NotRequired`, ID message). `messages` tidak diubah, jadi `/history` lengkap.
  - Ringkasan masuk `ContextBuilder.system_message(config, summary)` sebagai bagian sebelum
    lingkungan, bukan message tambahan.
  - Peringkasan: model yang sama tanpa tool, tag `skip_stream`, per batch jika backlog > anggaran.
    Respons kosong mempertahankan ringkasan lama. Error model tidak ditangkap.
  - Unit tunggal yang melebihi anggaran dipotong di salinan (penanda `[truncated]` ikut dihitung).
  - `SKIP_STREAM_TAG` dipindah ke `core/constants.py`.
- **Hasil ukur:** Ollama `qwen3.5:9b` (`context_length` 262144) membaca prompt 1,6k/13,5k/35k token
  tanpa pemotongan diam-diam. `count_tokens_approximately` 1–8% di atas hitungan Ollama.
  Smoke test anggaran 1000: satu peringkasan ±15 detik, dan fakta giliran pertama tetap diingat.
- **Pelajaran:**
  - `MessagesState` memakai `typing_extensions.TypedDict`. Mewarisi `typing.TypedDict` bersamaan
    dengannya menghasilkan `metaclass conflict`. Deklarasikan field langsung di state agent.
  - Return node berupa `{"messages": ..., **typed_dict}` dibaca pyrefly sebagai
    `dict[str, object]`. Buat `TypedDict` update sendiri dan isi field-nya secara eksplisit.
  - Respons `FakeModel` berputar. Test yang memicu beberapa panggilan ringkasan (batch) harus
    menyediakan respons yang cukup, kalau tidak hasilnya kembali ke respons pertama.
  - Agent tidak boleh menjalankan command git apa pun, termasuk `git diff` di dalam rangkaian
    perintah verifikasi (aturan user F21). Classifier menolak perintah itu.

### 2026-11-16: Skill built-in dari F28

- **Keputusan user:** `Project.skill_ids` = ID lengkap `<scope>/<name>`. `load_skill` di-bind hanya
  saat project punya skill aktif, termasuk di chatbot.
- **Keputusan desain:**
  - `harness/skills/`: `Skill` (model ADR 0005), `parse_skill_markdown` (spesifikasi agentskills.io),
    `FilesystemSkillSource` (`BUILTIN_SKILLS_DIR`), `SkillRegistry` (sumber pertama menang untuk ID
    sama), dan `SkillToolkit` (indeks prompt + `tools_for(config)`).
  - `load_skill(name, config, path=None)`: skill aktif dari `configurable["project_skill_ids"]`,
    resource harus tercatat (tidak ada akses file bebas), dibatasi 20.000 karakter.
  - `ChatbotAgent(ToolCallingAgent)` tanpa tool bawaan. `ToolCallingAgent` menyiapkan model dasar
    dan model + `load_skill`, lalu memilih per giliran.
  - Registry dibuat di `create_app`, dimuat di lifespan (`app.state.skill_registry`).
- **Pelajaran:**
  - `@tool` dengan parameter `config: RunnableConfig` menerima config run, dan parameter itu tidak
    masuk schema tool.
  - Untuk menguji model mana yang dipakai per giliran, `bind_tools` di FakeModel tiruan harus
    mengembalikan salinan berlabel dengan log bersama. Mencatat panggilan `bind_tools` saja hanya
    membuktikan binding saat build.
  - `"\\\\"` di string Python yang ditulis lewat script menjadi dua backslash di file. Doctest
    `_normalize_path` menangkapnya.
  - File data (`.md`) di dalam package ikut di wheel hatch tanpa konfigurasi tambahan. Diverifikasi
    lewat `uv build` dan test e2e.

### 2026-11-16: ContextBuilder dari F27

- **Keputusan user:** bagian lingkungan (tanggal + timezone) selalu ada di semua agent, walaupun
  prompt v1 berubah (chatbot kini punya system prompt).
- **Keputusan desain:**
  - `harness/context.py`: `PromptSection` (`max_chars`, penanda `[truncated]`) dan
    `ContextBuilder(instructions, clock, use_project_instructions, skills, memory)`. Urutan tetap:
    agent → project → skills → memory → environment. Bagian kosong dilewati.
  - Agent menerima `ContextBuilder` lewat konstruktor dan memanggil `system_message(config)` di
    node yang menerima `config`. Placeholder `{current_date}` dihapus dari prompt.
  - Expert supervisor tanpa instruksi project (`expert_context()`).
  - `Clock`/`local_now` di harness. Test layering harness melarang import `agents/`, `service/`,
    `schema/`, `client/`, `ui/`, `langchain`, dan `deepagents`.
- **Pelajaran:**
  - `SystemMessage.content` bertipe `str | list`. Untuk pyrefly, pakai `message.text`.
  - Saat menulis file lewat script Python di heredoc, `\n` di dalam string bisa berubah menjadi
    baris baru sungguhan di file tujuan. Periksa hasilnya atau pakai Edit.
  - `.env.example` jangan berisi nilai yang hanya cocok untuk satu provider. Developer menyalinnya
    apa adanya (`LLM_MAX_TOKENS_PARAM=max_completion_tokens` membuat batas token tidak berlaku di
    Ollama).

### 2026-11-15: Projects dari F26

- **Keputusan user:** route `/projects/{project_id}/...` (PRD §11 no. 8 terjawab). Model: request →
  project → default. Hapus project = hapus thread-nya. `ProjectSettings` hanya `max_tokens`.
- **Keputusan desain:**
  - `ProjectRepository` (memory, tanpa aturan akses) + `ProjectService` (service: 404/403/422,
    seed, hapus berantai). `ProjectRecord` memakai tipe biasa (`settings` berupa dict), karena
    `memory/` tidak boleh import `schema/`.
  - `base_agent_id` immutable. `owner_id` berisi `sub` token (Text, bukan FK ke users).
  - `project_id` di metadata run hanya untuk thread project. `is_thread_owner(..., project_id)`
    membandingkannya, sehingga `None` cocok dengan key yang tidak ada (thread lama).
  - `RunTarget` + `ProjectRunContext` di `service/run_input.py`. Kunci `configurable` project ada
    di `core/constants.py` dan juga di `RESERVED_AGENT_CONFIG_KEYS` (schema).
  - Built-in project sebagai data di `agents/catalog.py`, di-upsert di lifespan.
- **Pelajaran:**
  - Containment JSONB (`metadata @> filter`) tidak bisa memilih "key tidak ada", jadi listing
    thread tanpa project disaring di Python oleh cek pemilik.
  - Built-in yang di-upsert setiap startup tidak boleh diurutkan berdasarkan `updated_at`; urutan
    berubah setiap restart. Urutkan berdasarkan nama.
  - Iterasi `model_fields_set` (sebuah `set`) tidak berurutan. Iterasi `Model.model_fields`, lalu
    saring dengan `model_fields_set`, supaya hasilnya deterministik.
  - Mutation check (patahkan logika sebentar, pastikan test gagal) berguna saat test baru lulus
    di percobaan pertama.
