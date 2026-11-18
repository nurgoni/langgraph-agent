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

- **Fase:** M6 Frontend. F33 (Chat UI) selesai dan menunggu user commit, push, dan PR di branch
  `feature/F33-chat-ui`. E2E Compose F33 belum dijalankan (build image `web` terputus).
- **Berikutnya:** **F34** (Projects & threads UI), lalu rilis v0.6.0.
- **Repo:** remote `origin` = `https://github.com/nurgoni/langgraph-boilerplate-agent.git`.
  User yang melakukan push. CLI `gh` tidak terpasang, jadi PR dibuka lewat web.
- **Arsip:** Decision Log M0–M4 ada di
  [archive/decision-log-m0-m4.md](archive/decision-log-m0-m4.md), dan F26–F31 di
  [archive/decision-log-m4-m5.md](archive/decision-log-m4-m5.md).
- **Terakhir diperbarui:** 2026-11-17 (F33)

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

Ringkasan pelajaran dari M0–M5 yang masih berlaku (detail di arsip dan entri fitur terkait).

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

## Decision Log

### 2026-11-17: Chat UI dari F33

- **Keputusan user:** pemilih model saja di composer (agent selalu `default_agent`, agent lain lewat
  Project F34). Template registry assistant-ui boleh diedit (hanya `src/components/ui/` vendor).
  URL thread `/chat/:threadId`, chat baru di `/`.
- **Keputusan desain:**
  - assistant-ui 0.15.32 + react-markdown 0.14.24 (dipin persis). Registry meminta ^0.15.36 yang
    belum lolos jeda 14 hari; template diambil dari JSON registry (`r.assistant-ui.com/<nama>.json`,
    butuh curl karena User-Agent Python ditolak 403) dan lolos tsc dengan 0.15.32.
    `elements/` disalin apa adanya (override ESLint per folder), `thread.tsx` dipangkas.
  - Tipe SSE dari `contracts/stream-event.schema.json` lewat `scripts/stream-events.mjs`
    (json-schema-to-typescript, mode `--check`), bagian dari `generate:api`/`check:api`.
  - `ChatController` di luar React (`useSyncExternalStore`) dengan `generation` untuk membuang hasil
    terlambat saat pindah thread. `conversation.ts` murni: satu message asisten per pesan user,
    `parentId` = nama expert, status `incomplete/length|error|cancelled`.
  - Kedua route chat memakai `ChatPage` yang sama, jadi state tidak hilang saat URL chat baru
    diganti ke `/chat/<id>` (tidak ada request `/history`).
  - Dockerfile `web`: cache mount BuildKit untuk store pnpm.
- **Hasil ukur:** rekaman Ollama `qwen3.5:9b`: reasoning 18 dtk (224 frame reasoning), tool call
  4 dtk, supervisor 10 dtk, terpotong (600 token) 12 dtk. Bundle 1,1 MB (337 kB gzip), belum
  code-split.
- **Pelajaran:**
  - `TextDecoderStream` bentrok dengan tipe lib TS (`BufferSource`); pakai `TextDecoder` dengan
    `{ stream: true }`.
  - jsdom butuh polyfill `ResizeObserver`, `scrollTo`, `scrollIntoView` untuk viewport assistant-ui.
  - `new Request(request)` memakai body request asli; di wrapper `fetch` test, baca `input.url`.
  - Lint `react-hooks/refs` melarang ref dibaca lewat callback di initializer `useState`; pasang
    listener lewat effect.
  - Mutation check menemukan guard `generation` di loop event tidak teruji, karena abort mematikan
    stream; test baru memakai body yang mengabaikan abort.
  - Rekaman `.sse` diakhiri `\n\n`, dan hook `end-of-file-fixer` memotongnya saat user commit.
    Fixture dikecualikan dari hook itu. File data baru: cek hook pre-commit sebelum handoff.

### 2026-11-17: Frontend scaffold dari F32

- **Keputusan user:** pnpm lewat corepack (`packageManager` di-pin), Node 24 LTS, token di
  `sessionStorage`, API lewat proxy same-origin `/api` (nginx image `web`, proxy Vite di dev),
  tanpa CORS.
- **Keputusan desain:**
  - Versi diresolusi pnpm dengan `minimumReleaseAge: 20160` (14 hari, setara `exclude-newer` uv)
    di `frontend/pnpm-workspace.yaml`. TypeScript dipin `~5.9.3`: typescript-eslint 8.72 (`<6.1`)
    dan openapi-typescript 7.13 (`^5`) belum mendukung TypeScript 7.
  - shadcn base Radix + paket `cn` (milik shadcn, diverifikasi maintainer dan repo). Vendor
    `src/components/ui/` dan `src/hooks/use-mobile.ts` tidak diedit. ESLint mematikan tiga aturan
    hanya untuk file vendor.
  - Base URL client absolut `<origin>/api`; URL service tidak di-bake ke build. `API_UPSTREAM`
    image `web` lewat template envsubst nginx.
  - `SessionStore` menyimpan `expiresAt` absolut dan membuang sesi kedaluwarsa/rusak saat dibaca.
    Logout otomatis hanya untuk 401 pada request yang membawa token (login salah tidak memicunya).
  - Drift tipe API dicek oleh `pnpm check:api` (CI) dan hook `frontend-check`.
  - Rencana commit 1–4 ROADMAP digabung: scaffold, vendor, client, dan login saling bergantung
    untuk lolos `tsc` dan ESLint.
- **Hasil ukur:** build image `web` pertama 4493 detik (registry npm sangat lambat, bukan
  Dockerfile); install lokal 7–36 menit. Bundle 480 kB (155 kB gzip).
- **Pelajaran:**
  - CLI shadcn memanggil `pnpm` langsung. Tanpa `corepack enable`, buat shim `pnpm.cmd` di
    scratchpad yang memanggil `corepack pnpm`, lalu tambahkan ke PATH.
  - openapi-fetch dengan base URL relatif (`/api`) gagal di jsdom karena `new Request()` butuh URL
    absolut.
  - `corepack pnpm --dir frontend` dari root memakai pnpm default corepack (bukan versi
    `packageManager`), dan pnpm gagal `ERR_PNPM_BAD_PM_VERSION`. Ditemukan di cek akhir, bukan
    saat implementasi, karena semua cek sebelumnya dijalankan dari dalam `frontend/`.
  - Exit code `check:api` tertutup pipe (`| tail`); verifikasi exit code tanpa pipe.
  - jsdom tidak punya `matchMedia`, padahal sidebar shadcn memakainya: polyfill di
    `src/test/setup.ts`.
  - `pnpm-lock.yaml` pnpm 12 berisi dua dokumen YAML; hook `check-yaml` butuh
    `--allow-multiple-documents`. Ditemukan saat user commit (tidak ada cek lokal yang menjalankan
    `check-yaml`).
  - File hasil CLI bisa tanpa newline di akhir; hook `end-of-file-fixer` akan mengubahnya saat
    commit.

### 2026-11-17: Dev-time skill dan arsip memory

- **Keputusan user:** skill di `.claude/skills/` (dipicu otomatis oleh Claude Code, dan didaftar
  di AGENTS.md § Dev-time Skill untuk agent lain). Empat skill: `feature-workflow`,
  `git-handoff`, `release`, `memory-maintenance`. memory.md diarsipkan sekarang. Skill dikerjakan
  di branch `chore/dev-time-skills` sebelum F32.
- **Keputusan desain:**
  - Skill hanya berisi urutan kerja dan merujuk ke AGENTS.md, CONTRIBUTING.md, dan ROADMAP untuk
    aturannya, supaya aturan tidak tersalin di dua tempat.
  - `feature-workflow/references/smoke_template.py`: smoke test model asli di database sementara
    (diverifikasi dengan `qwen3.5:9b`).
  - Decision Log M0–M4 dipindah utuh ke `.agents/archive/decision-log-m0-m4.md`, termasuk tabel
    "Pelajaran dari Kode Lama" (port sudah selesai). memory.md mendapat § Aturan Kerja dan
    § Pelajaran Lintas Fitur sebagai ringkasan yang masih berlaku (890 → ±290 baris).
  - `.claude/settings.local.json` di-gitignore. Hanya `.claude/skills/` yang dibagikan.

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

## TODO Berikutnya

- [ ] User: isi `FIRECRAWL_API_KEY` di `.env`, lalu minta agent menjalankan smoke test Firecrawl
      asli.
- [ ] User: set `develop` sebagai default branch dan aktifkan branch protection, jika belum
      (CONTRIBUTING.md § Setup Awal Repo).
- [ ] Setelah F32: pertimbangkan skill `api-contract-change` (ubah schema → export kontrak →
      generate tipe TS), pemicu dev-time skill berikutnya.
