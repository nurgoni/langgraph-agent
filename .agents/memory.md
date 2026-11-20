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
- **Berikutnya:** M8 Data Analytics, mulai **F39** (SQL data source).
- **Repo:** remote `origin` = `https://github.com/nurgoni/langgraph-boilerplate-agent.git`.
  User yang melakukan push. CLI `gh` tidak terpasang, jadi PR dibuka lewat web.
- **Arsip:** Decision Log M0–M4 ada di
  [archive/decision-log-m0-m4.md](archive/decision-log-m0-m4.md), F26–F31 di
  [archive/decision-log-m4-m5.md](archive/decision-log-m4-m5.md), dan dev-time skill + F32–F34 di
  [archive/decision-log-m6.md](archive/decision-log-m6.md).
- **Terakhir diperbarui:** 2026-11-19 (audit dokumen + ERD, menunggu user commit/PR)

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
- **Dokumen umum ikut usang:** fitur cenderung hanya menambah bagiannya sendiri. Di akhir fitur,
  periksa juga bagian umum ARCHITECTURE.md, status README, dan PRD §7–§8, serta `DATA_MODEL.md`.
- **Hook pre-commit pada file data:** `end-of-file-fixer` mengubah fixture yang sengaja diakhiri
  `\n\n` (dikecualikan), dan `check-yaml` butuh `--allow-multiple-documents` untuk lockfile pnpm.

## Decision Log

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

### 2026-11-18: Artifact panel UI dari F38

- **Keputusan user:** panel kanan Resizable (Sheet di layar sempit); upload saat file dipilih;
  gambar markdown dicocokkan ke artifact jawaban yang sama; papaparse untuk CSV.
- **Keputusan desain:**
  - Artifact asisten = part `data` `artifacts`; artifact pesan user di `metadata.custom.artifacts`
    (lampiran assistant-ui tidak membawa ukuran). `ArtifactCards` membuka panel lewat context.
  - Isi lewat fetch bertoken → `Blob` → object URL (TanStack Query, tidak dicabut karena StrictMode).
  - Chip composer dari primitive assistant-ui + shadcn, tanpa template registry `attachment`
    (butuh `avatar`, `use-attachment-src`, `zustand`). Adapter upload di `add` (async generator).
  - Grup `Resizable` selalu dirender supaya chat tidak di-mount ulang.
  - Dependency baru: `papaparse` 5.7.0, `react-resizable-panels` 4.18.0 (shadcn `resizable`,
    `table`). react-resizable-panels v4: angka = piksel, string `"55%"` = persen.
- **Hasil ukur:** 86 test Vitest (+19), mutation check 11/11, e2e Compose 19/19 (image `web`
  dengan dependency baru ter-build di percobaan pertama). Bundle 1,36 MB (415 kB gzip).
- **Pelajaran:**
  - Vitest membungkus `Request` agar menerima Blob/FormData jsdom, tetapi File di dalam FormData
    menjadi Blob bernama "blob", dan undici tidak bisa membaca File jsdom. Setup test memakai
    `File` (node:buffer) dan `FormData` Node; `Blob` tetap jsdom supaya kompatibilitas lain jalan.
  - Membuat `new Request(request)` di wrapper test menghabiskan body request asli (probe palsu
    gagal "unreachable"); untuk debug, panggil service palsu langsung.
  - `ComposerPrimitive.AddAttachment` membuat `<input type=file>` dinamis lalu `click()`; di test,
    spy `HTMLInputElement.prototype.click`, isi `files`, lalu kirim event `change`.

### 2026-11-18: Sandbox dari F37

- **Keputusan user:** service `sandbox-runner` (satu-satunya dengan `docker.sock`, HTTP internal +
  `SANDBOX_TOKEN`); `ProjectSettings.tool_approval` default `never`; `run_python`/`run_shell` untuk
  chatbot + research jika `SANDBOX_URL` diisi; timeout 60 detik.
- **Keputusan desain:**
  - `DockerSandbox` lewat Docker Engine API (httpx UDS), satu container per eksekusi: `network=none`,
    rootfs read-only, UID 10001, tanpa capability, `no-new-privileges`, 512 MB / 1 CPU / 128 pids,
    `/tmp` tmpfs, `/workspace` volume anonim; container + volume selalu dihapus.
  - `ExecutionRequest`/`ExecutionResult` = body HTTP runner; `bytes` + `ser_json_bytes`/
    `val_json_bytes="base64"` (bukan `Base64Bytes`, yang juga men-decode input Python).
  - Sandbox masuk `HarnessContext`; `ArtifactService` meneruskannya ke `run_context()`.
  - Compose `sandbox-image` (build lalu selesai) + `sandbox-runner` (target Dockerfile baru, root).
  - Test AST NFR-10 di `service/`, `agents/`, `harness/`, `sandbox/`.
- **Hasil ukur:** 1102 pytest (+41), mutation check 15/15, e2e Compose 19/19 (jaringan diblokir,
  loop berhenti 3 dtk, pandas menulis file, agent-service tanpa `docker.sock`). Smoke
  `qwen3.5:9b` + runner sementara: `read_file` → `run_python` (pandas + matplotlib, total benar) →
  `share_file chart.png` (19.341 byte) dalam 23,1 dtk; sapaan tanpa tool 1,0 dtk. Image sandbox
  519 MB.
- **Pelajaran:**
  - Probe Docker: `docker cp` ke volume container yang belum start berhasil, tetapi volume anonim
    milik root kecuali image membuat foldernya dengan pemilik user sandbox. Tmpfs tidak bisa diisi
    sebelum start.
  - Di Git Bash, `docker` dengan path `/workspace` diubah menjadi path Windows; pakai
    `MSYS_NO_PATHCONV=1`.
  - Script Python di dalam string test e2e: tulis `\\n` (escape dua kali), kalau tidak literal bytes
    terputus (gagal hanya di e2e).
  - Model menyisipkan `![...](chart.png)` (path workspace) di jawaban; F38 perlu menampilkan
    artifact dari tool message, bukan link markdown itu.

### 2026-11-18: Workspace & file tools dari F36

- **Keputusan user:** tool file selalu untuk chatbot + research assistant; lampiran disalin ke
  workspace `uploads/<nama>`; `TOOL_OUTPUT_MAX_TOKENS` 4.000; `grep` teks literal.
- **Keputusan desain:**
  - Workspace + penerbit artifact lewat runtime context LangGraph (`HarnessContext`,
    `ainvoke(..., context=...)`), tanpa mengubah `BaseAgent.build`. Tool memakai
    `ToolRuntime[HarnessContext]`; thread/user dari config service.
  - `PostgresWorkspace` di `memory/workspace.py` (tabel `workspace_files`, revisi `0007`, isi
    `BYTEA`, batas = `ARTIFACT_MAX_BYTES`); protocol + `InMemoryWorkspace` di `files/workspace.py`.
  - Offloader di `ToolNode(awrap_tool_call=...)`; `read_file`/`list_files`/`grep` dikecualikan.
  - `share_file` → `ToolMessage.additional_kwargs["artifacts"]` lewat `ArtifactService.publish`.
  - Path lampiran untuk model di `additional_kwargs["workspace_files"]`, ditambahkan hanya ke
    salinan pesan untuk model.
- **Hasil ukur:** 1061 pytest (+50), mutation check 16/16, e2e Compose 17/17. Smoke
  `qwen3.5:9b`: lampiran CSV → `read_file uploads/sales.csv` dan total benar (17,4 dtk); tulis +
  bagikan → `write_file` lalu `share_file` dengan artifact (4,2 dtk); sapaan tanpa tool (1,0 dtk).
- **Pelajaran:**
  - `context_schema` di `StateGraph` tidak dibutuhkan agar `ToolRuntime.context` terisi, dan
    menspesialisasi `StateGraph[TypedDict, ...]` memicu error pyrefly baru; tanpa schema tidak ada
    suppression tambahan.
  - `ToolRuntime` tanpa parameter tipe memicu peringatan serializer Pydantic (context dianggap
    `None`); field context bertipe `Protocol` butuh `@runtime_checkable`.
  - Doctest mengubah tab di docstring menjadi spasi; contoh dengan tab ditulis lewat `repr`.
  - `ORDER BY` teks di Postgres memakai collation locale yang mengabaikan tanda baca, jadi urutan
    `sales-x.csv` vs `sales.csv` berubah-ubah (test flaky). Listing memakai `COLLATE "C"`.
  - Wiring `context=` di route tidak teruji oleh `FakeModel` default; test memakai agent dengan
    model terskrip yang memanggil `write_file` lewat API (invoke dan stream).

### 2026-11-18: Artifact storage dari F35

- **Keputusan user:** lampiran lewat `artifact_ids` di input run; artifact ikut terhapus bersama
  thread, ditambah `DELETE /artifacts/{id}`; `ARTIFACT_MAX_BYTES` 25 MB; semua tipe diterima,
  unduhan selalu `attachment` + `nosniff` (+ CSP `sandbox`).
- **Keputusan desain:**
  - Satu artifact satu thread (`artifacts.thread_id`), ditautkan saat pertama dikirim; thread lain
    → 409, lampiran untuk jawaban interrupt → 422. Ditautkan setelah kepemilikan thread lolos
    (`build_attached_run_input`).
  - `ThreadRepository(cleanups=[...])` (`ThreadDataCleanup`) menghapus artifact di jalur hapus
    thread dan hapus project.
  - `LocalArtifactStore`: anyio, tulis ke `.part` lalu rename, kunci divalidasi pola.
  - nginx `client_max_body_size ${API_MAX_BODY_SIZE}`; `python-multipart` eksplisit di extra.
  - Fixture autouse `artifact_dir` di `tests/conftest.py` (env `ARTIFACT_DIR` → tmp_path).
- **Hasil ukur:** 1011 pytest (+37), mutation check 12/12, e2e Compose 16/16 dalam 82 detik
  (upload 2 MB lewat proxy `web`, bertahan setelah restart, user lain 404).
- **Pelajaran:**
  - Tanpa fixture `artifact_dir`, lifespan test membuat `data/artifacts` di repo (ditemukan dari
    folder kosong setelah pytest). `data/` sekarang di `.gitignore`.
  - FastAPI membaca body multipart sebelum handler, jadi batas ukuran baru ditegakkan saat
    menyalin; proxy nginx adalah penahan pertama.
  - E2E fitur sebelumnya dijalankan dari salinan repo di scratchpad (`uv run` di folder salinan),
    supaya pengerjaan fitur berikutnya di working tree tidak ikut ter-build.
  - Insiden rilis v0.6.0 (diperiksa dengan git read-only atas izin user): PR release → `main` tidak
    di-merge, tag dibuat di `main` lama (menunjuk commit v0.5.0), dan `git branch -d` tetap
    menghapus branch release karena sudah ter-push. Commit rilis diselamatkan dari reflog. Daftar
    command rilis kini meminta user memastikan PR **Merged** dan memeriksa `git log` sebelum tag.
  - Squash PR #40 (F34) memakai judul F33; tidak diperbaiki karena butuh force-push ke `develop`.

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
- [ ] User: pasang ruleset GitHub (CONTRIBUTING.md § Setup Awal Repo): `main` hanya "Merge",
      `develop` hanya "Squash", default commit squash = judul PR, blokir force-push. Mencegah
      ulang insiden squash rilis v0.7.0 dan judul squash yang salah (#40, #45).
- [ ] Usulkan ke user (dari audit ERD 2026-11-19): retensi `run_traces` atau hapus bersama thread,
      pembersihan artifact yatim (`thread_id` NULL lebih dari N jam), dan kebijakan hapus user.
- [ ] Setelah F32: pertimbangkan skill `api-contract-change` (ubah schema → export kontrak →
      generate tipe TS), pemicu dev-time skill berikutnya.
