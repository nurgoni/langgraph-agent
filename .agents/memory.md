# Project Memory

Memori kerja untuk coding agent dan kontributor. Baca sebelum mulai bekerja dan perbarui setelah
ada keputusan penting (lihat Definition of Done di [AGENTS.md](../AGENTS.md)). Prosedur kerja
berulang ada di dev-time skill `.claude/skills/` (daftar di AGENTS.md § Dev-time Skill).

**Aturan file ini** (skill `memory-maintenance`):

- Entri Decision Log bersifat append-only, dan entri terbaru ditaruh **paling atas**.
- Entri yang salah tidak dihapus. Tambahkan entri baru yang membatalkannya ("Supersedes: ...").
- Jaga file tetap ringkas (< ~300 baris) karena dimuat otomatis di setiap sesi. Entri milestone
  yang sudah dirilis dipindah utuh ke `.agents/archive/`, dan keputusan besar ke `docs/adr/`.
- Tanggal ditulis absolut (YYYY-MM-DD).

## Status Saat Ini

- **Fase:** v0.7.0 (M7 Files & Execution) dirilis 2026-11-18. PR release #46 ter-squash ke `main`;
  back-merge ke `develop` diselesaikan agent 2026-11-19 (`efe7364`, menunggu user push `develop`
  dan menghapus `release/v0.7.0` remote).
- **Berikutnya:** M8 Analytics Core (direvisi 2026-11-26): F47 → F39 → F48 → F49 → F50 → F40,
  mulai **F47** (step budget & retry guard). Dokumen revisi menunggu user commit/PR.
- **Repo:** remote `origin` = `https://github.com/nurgoni/langgraph-boilerplate-agent.git`.
  User yang melakukan push. CLI `gh` tidak terpasang, jadi PR dibuka lewat web.
- **Arsip:** Decision Log M0–M4 ada di
  [archive/decision-log-m0-m4.md](archive/decision-log-m0-m4.md), F26–F31 di
  [archive/decision-log-m4-m5.md](archive/decision-log-m4-m5.md), dev-time skill + F32–F34 di
  [archive/decision-log-m6.md](archive/decision-log-m6.md), dan F35–F38 di
  [archive/decision-log-m7.md](archive/decision-log-m7.md).
- **Terakhir diperbarui:** 2026-11-26 (revisi strategi M8 code-as-action)

## Aturan Kerja

Keputusan user yang berlaku untuk semua pekerjaan. Detail asalnya ada di arsip.

- **Git dijalankan user** (F21): agent tidak menjalankan command git apa pun, termasuk yang
  read-only (`git status`, `git diff`, `git log`), juga di dalam rangkaian perintah verifikasi.
  Agent menulis daftar command (skill `git-handoff`). Branch dihapus lokal dan remote segera
  setelah di-merge.
- **Bahasa:** dokumen, docstring, dan komentar berbahasa Indonesia. Identifier, pesan error/log,
  commit message, docstring `@tool`, prompt agent, dan teks UI berbahasa Inggris.
- **Langkah 1 setiap fitur:** keputusan yang ambigu ditanyakan ke user sebelum menulis kode, dan
  jawabannya dicatat di ROADMAP (Langkah 1) dan Decision Log.
- **Class sebagai default**, function hanya untuk kasus di AGENTS.md § Class vs Function.
- **Settings:** nama field huruf kecil, `env_ignore_empty=True`. Test membuat `Settings` dengan
  `_env_file=None` supaya `.env` developer tidak terbaca.

## Pelajaran Lintas Fitur

Ringkasan pelajaran dari M0–M6 yang masih berlaku (detail di arsip dan entri fitur terkait).

- **Windows + psycopg:** async psycopg butuh `SelectorEventLoop` (uvicorn:
  `loop="asyncio:SelectorEventLoop"`). Pakai `127.0.0.1`, bukan `localhost`, untuk port compose.
  Selalu set `connect_timeout` (default 130 detik).
- **Windows + uv:** `uv sync`/`uv remove` gagal saat service/UI yang memakai paket masih berjalan;
  pakai `--no-sync`, lalu sync setelah proses berhenti. `uv lock --offline` cukup untuk bump versi.
- **Edit file lewat shell:** heredoc panjang atau berisi banyak backtick bisa gagal di-parse, dan
  `\n` di string Python bisa menjadi baris baru sungguhan. Tulis script ke scratchpad lalu
  jalankan, atau pakai Edit. Periksa hasilnya.
- **pyrefly:** `StateGraph(TypedDict)` perlu `# pyrefly: ignore[bad-specialization]`. Override
  method wajib punya semua parameter induk. Return node berupa TypedDict update eksplisit, bukan
  `{**typed_dict}`. `SystemMessage.text`, bukan `.content`. Hindari suppression lain; cari tipe yang
  benar (`UsageMetadata`, `dataclasses.replace`).
- **Hook pre-commit:** pyrefly memeriksa file untracked, dan perubahan yang belum di-stage
  disimpan sementara. File untracked yang bergantung pada perubahan commit berikutnya harus
  disingkirkan sementara. `ruff format --check .` juga memformat blok Python di Markdown.
- **Test:** pytest `--import-mode=importlib`, jadi file test tidak saling import dan fixture
  `conftest.py` hanya berlaku di foldernya. `ASGITransport` tidak menjalankan lifespan. Respons
  `FakeModel` berputar. Tabel migrasi baru masuk `KEPT_TABLES` di `tests/conftest.py`.
- **Verifikasi:** mutation check (patahkan logika sebentar lewat Edit, pastikan test gagal, lalu
  kembalikan) untuk test yang lulus di percobaan pertama, tetapi jangan saat e2e Docker sedang
  build. Smoke test dengan model asli (Ollama `qwen3.5:9b`) adalah satu-satunya cara menangkap
  perilaku provider; jalankan di database sementara, bukan database dev.
- **LangGraph:** reducer `add_messages` mengisi `id` in-place, jadi selalu kembalikan objek message
  baru. `interrupt()` di dalam tool menjalankan ulang semua tool call giliran itu saat dilanjutkan.
  Callback dan config diwariskan ke node dan sub-graph.
- **Frontend:** pnpm lewat `corepack pnpm` dari dalam `frontend/` (corepack membaca
  `packageManager` dari folder kerja, bukan `--dir`; dari root pakai `corepack pnpm@<versi>`,
  seperti hook `frontend-check`). Tanpa `corepack enable` global. Registry npm
  lambat: install dan build image `web` dijalankan di background. Setelah `contracts/` berubah,
  jalankan `generate:api`. Kode aplikasi tidak mengedit vendor shadcn.
- **shadcn CLI:** butuh `pnpm` di PATH (shim `pnpm.cmd` → `corepack pnpm` di scratchpad), dan
  berhenti diam-diam (exit 0) di prompt overwrite; jawab `n` lewat stdin lalu cek file yang ditulis.
- **jsdom:** butuh polyfill `matchMedia`, `ResizeObserver`, `scrollTo`, `scrollIntoView`
  (`src/test/setup.ts`). openapi-fetch butuh base URL absolut. Daftar yang di-mount ulang selalu
  fetch ulang, jadi invalidasi query diuji lewat daftar yang tetap ter-mount.
- **E2E Docker:** build image `web` bisa melewati `BUILD_TIMEOUT_SECONDS` (900) atau putus karena
  registry. Build image terpisah tanpa timeout (dengan retry), lalu jalankan e2e. Untuk menguji fitur
  sebelumnya sambil mengerjakan fitur baru, jalankan e2e dari salinan repo di scratchpad.
- **Sandbox Docker (F37, relevan untuk F49):** volume anonim milik root kecuali image membuat
  foldernya untuk UID sandbox, tmpfs tidak bisa diisi sebelum container start, dan di Git Bash
  path `/workspace` diubah menjadi path Windows (pakai `MSYS_NO_PATHCONV=1`). Script Python di
  dalam string test e2e butuh `\\n`.
- **Postgres + workspace:** `ORDER BY` teks memakai collation locale, jadi listing yang urutannya
  harus stabil memakai `COLLATE "C"`. `ToolRuntime` harus diberi parameter tipe
  (`ToolRuntime[HarnessContext]`).
- **Dokumen umum ikut usang:** fitur cenderung hanya menambah bagiannya sendiri. Di akhir fitur,
  periksa juga bagian umum ARCHITECTURE.md, status README, dan PRD §7–§8, serta `DATA_MODEL.md`.
- **Hook pre-commit pada file data:** `end-of-file-fixer` mengubah fixture yang sengaja diakhiri
  `\n\n` (dikecualikan), dan `check-yaml` butuh `--allow-multiple-documents` untuk lockfile pnpm.

## Decision Log

### 2026-11-26: Revisi M8 menjadi code-as-action

- **Supersedes:** urutan M8–M10 di "2026-11-15: Rencana Fase 2", rencana awal F39/F40 (tiga tool
  SQL, semantic layer sebagai skill `demo-metrics`, acceptance satu skenario), dan keputusan F37
  "satu container per eksekusi" untuk `run_python`.
- **Keputusan user (semua usulan disetujui):**
  - M8 dipecah: **M8 Analytics Core** (F47 → F39 → F48 → F49 → F50 → F40, `v0.8.0`) dan **M9
    Scheduled Analytics** (F41, F42, `v0.9.0`). Knowledge menjadi M10, Interop M11.
  - Kernel per thread (F49) dikerjakan **sebelum** F40.
  - Akses database **hanya lewat `run_sql` di service**. Sandbox tetap tanpa jaringan dan tanpa
    kredensial DB ([ADR 0007](../docs/adr/0007-code-as-action-execution.md)).
  - Semantic layer = **data catalog YAML terstruktur** per data source, sedangkan metode analisa
    tetap skill ([ADR 0006](../docs/adr/0006-data-catalog-semantic-layer.md)).
  - **Registry beberapa data source** sejak awal, dipilih per project (`data_source_ids`).
  - Batas retry berlaku untuk **semua tool**: 3 kegagalan beruntun pada tool yang sama.
- **Keputusan desain:**
  - Prinsip: agent diberi primitif (eksplorasi, query, kernel), pengetahuan (katalog + playbook),
    dan loop kerja (rencana, verifikasi, batas retry), bukan fungsi per skenario. Coverage diukur
    dengan eval lintas dua dataset demo dari domain berbeda (NFR-13).
  - Loop hipotesis untuk pertanyaan "kenapa" adalah **playbook skill**, bukan graph khusus. Rencana
    dibuat model per pertanyaan (`update_plan`), tanpa routing yang di-hardcode.
  - Ditunda ke backlog: tampilan rencana di UI (B8), uji hipotesis paralel (B9), LLM judge (B10),
    katalog lewat UI (B11). MicroVM tetap B5. Compiler metrik ditolak.
- **Temuan yang memicu revisi:** `recursion_limit` tidak pernah diatur, sehingga default LangGraph
  terpasang (10.007) praktis tanpa batas. Belum ada batas retry. `run_python` kehilangan state di
  setiap pemanggilan.

### 2026-11-19: Audit dokumentasi dan ERD

- **Temuan:** bagian umum `docs/ARCHITECTURE.md` (Gambaran Besar masih `v0.3.0`, Layer, Siklus
  Hidup, tabel Error, Client masih menyebut ID user dari header, Deployment, Testing) dan awal
  `README.md` (status `v0.1.0`, daftar fitur, diagram) usang. Penyebabnya, setiap fitur hanya
  menambah bagiannya sendiri. `PRD.md` §7–§8 juga belum sinkron (endpoint F30/F31/F35 masih di
  tabel rencana, schema tanpa `truncated`/`artifacts`/`tool_approval`).
- **Keputusan desain:** ERD ditulis di `docs/DATA_MODEL.md` (Mermaid), bukan di ARCHITECTURE.md.
  Thread digambar sebagai entitas virtual, karena tidak punya tabel. Definition of Done
  (`AGENTS.md`) dan skill `feature-workflow` § 6 kini mewajibkan bagian umum ARCHITECTURE.md dan
  `DATA_MODEL.md` ikut diperbarui.
- **Temuan model data:** tidak ada foreign key, jadi penghapusan berantai dilakukan aplikasi
  (`ThreadRepository._remove`, `ProjectService.delete`). `run_traces` tidak ikut terhapus saat
  thread/project dihapus. Artifact yang di-upload tetapi tidak pernah dikirim (`thread_id` NULL)
  tidak dibersihkan otomatis. Tidak ada endpoint hapus user.
- **Pelajaran:** `pre-commit run` memanggil git secara internal, jadi tidak dipakai agent. Cek
  dokumen cukup `ruff format --check .` + script whitespace/EOF/link. Komentar atribut Mermaid
  `erDiagram` dihindarkan dari `{ } < > |`.

### 2026-11-19: Rilis v0.7.0 ter-squash, perbaikan workflow merge

- **Kejadian:** PR release #46 (`release/v0.7.0` → `main`) di-squash, bukan merge commit. Isi `main`
  (`9bafd36`) dan tag `v0.7.0` benar (`git diff release/v0.7.0 main` kosong), tetapi `main` tidak
  memuat commit `develop`, jadi back-merge konflik di `CHANGELOG.md` dan `.agents/memory.md`.
- **Perbaikan (git dijalankan agent atas izin user, khusus tugas ini):** konflik diambil dari versi
  `main` (`git checkout --theirs`), index diverifikasi identik dengan `main`, lalu back-merge
  di-commit (`efe7364`). `main` kembali menjadi leluhur `develop`. Push gagal dari terminal agent
  (kredensial HTTPS tidak tersedia), jadi push tetap oleh user. Aturan "git dijalankan user"
  tetap berlaku untuk pekerjaan lain.
- **Pencegahan:** CONTRIBUTING § Setup Awal Repo kini memakai ruleset per branch (`main` hanya
  Merge, `develop` hanya Squash, default commit squash = judul PR). § Release dan skill `release`
  mendapat langkah pemulihan "jika release terlanjur di-squash". Skill `git-handoff` mengingatkan
  pemeriksaan judul commit squash (#40 memakai judul F33, #45 memakai nama branch).

### 2026-11-15: Rencana Fase 2 (M4–M10)

- **Keputusan user:**
  - **Postgres-only**, dijalankan sebagai service di Docker Compose
    ([ADR 0001](../docs/adr/0001-postgres-only.md)).
  - **Harness dibangun sendiri**, tanpa `deepagents` atau package `langchain`
    ([ADR 0002](../docs/adr/0002-own-harness.md)). Alasan: belum ada waktu meriset perilakunya.
  - **Frontend React + TypeScript** dengan komponen standar (shadcn/ui, assistant-ui), tanpa
    komponen buatan sendiri, dan layout ala Claude dengan Projects
    ([ADR 0003](../docs/adr/0003-frontend-stack.md)). Streamlit menjadi dev console.
  - **Project = agent deklaratif** ([ADR 0004](../docs/adr/0004-project-as-declarative-agent.md)).
  - **Skill runtime built-in dulu** (`SKILL.md`, spesifikasi agentskills.io), untuk demo
    showcase. Skill lewat UI = backlog B1, tetapi setiap desain wajib menyediakan titik
    ekstensinya ([ADR 0005](../docs/adr/0005-skill-format-and-sources.md)).
  - Cron job: hasil analisa dikirim sebagai PDF di thread chat. Sumber data: database relasional.
- **Keputusan desain:**
  - Urutan: M4 Foundation → M5 Harness Core → M6 Frontend (demo) → M7 Files & Execution → M8 Data
    Analytics → M9 Knowledge → M10 Interop. Auth per user (F24) naik ke M4 karena frontend
    browser tidak boleh memegang `AUTH_SECRET`.
  - Fitur "general tools" (read/write/bash) dilebur ke F36 (workspace) dan F37 (sandbox). "Review"
    adalah skill/sub-agent, bukan tool.
  - Kode buatan model tidak pernah dijalankan di proses service (NFR-10). Referensi
    `charting_agent.py` (abh2050/langgraph_data_analytics_agents) memakai `exec()` tanpa sandbox,
    dan pola itu tidak ditiru.
  - Worker menjalankan agent lewat `AgentClient` dengan service account. Jendela waktu job dihitung
    dari waktu jadwal (UTC), dan `(job_id, window_start)` unik.
- **Di luar roadmap (ide user, jangan dijadwalkan):** memisahkan produk chat dari dev-time harness,
  seperti Claude memisahkan Claude Code dari chat biasa.
- **Pelajaran:** heredoc bash yang sangat panjang gagal dengan `ENAMETOOLONG`. Tulis konten ke file
  scratchpad, lalu `cat >>`.

## Pertanyaan Terbuka

Sinkron dengan [PRD.md §11](../PRD.md#11-open-questions). Dijawab di Langkah 1 fitur terkait:

- No. 6: sumber data analisa, user read-only, dan masking PII (F39).
- No. 9: library PDF (F42).
- No. 10: parser dokumen ingestion (F43).
- No. 11: profiling tabel besar (F39).
- No. 12: implementasi kernel per thread (F49).

## TODO Berikutnya

- [ ] User: isi `FIRECRAWL_API_KEY` di `.env`, lalu minta agent menjalankan smoke test Firecrawl
      asli.
- [ ] User: pasang ruleset GitHub (CONTRIBUTING.md § Setup Awal Repo): `main` hanya "Merge",
      `develop` hanya "Squash", default commit squash = judul PR, blokir force-push. Mencegah
      ulang insiden squash rilis v0.7.0 dan judul squash yang salah (#40, #45).
- [ ] Usulkan ke user (dari audit ERD 2026-11-19): retensi `run_traces` atau hapus bersama thread,
      pembersihan artifact yatim (`thread_id` NULL lebih dari N jam), dan kebijakan hapus user.
- [ ] Setelah F32: pertimbangkan skill `api-contract-change` (ubah schema → export kontrak →
      generate tipe TS), pemicu dev-time skill berikutnya.
