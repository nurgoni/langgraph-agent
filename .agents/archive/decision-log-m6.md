# Decision Log M6 dan dev-time skill (arsip)

Dipindah utuh dari `.agents/memory.md` pada 2026-11-18 (skill `memory-maintenance`), setelah
v0.6.0 (M6 Frontend) dirilis. Entri terbaru di atas. Pelajaran yang masih berlaku diringkas di
memory.md § Pelajaran Lintas Fitur.

### 2026-11-18: Projects & threads UI dari F34

- **Keputusan user:** Recents = chat umum saja (`GET /threads`), chat project di halaman project.
  Composer di halaman project (`/projects/:id`, chat di `/projects/:id/chat/:threadId`). Form
  shadcn + react-hook-form + zod.
- **Keputusan desain:**
  - `ChatService(api, projectId)` memilih route `/projects/{id}/...`. `ProjectChatPage` memberi
    `key={projectId}` ke `ChatPage`; halaman project = `ChatPage` dengan `welcome` = ringkasan
    project, daftar chat, dan aksi.
  - `ChatController.setRunListeners` (`onThreadCreated`, `onRunFinished`) menggantikan
    `setThreadCreatedListener`. Query thread di-invalidate saat thread dibuat dan setiap run selesai.
  - Helper `requireData`/`requireOk` + `ServiceError` (`src/api/service-error.ts`) untuk query dan
    mutation. `useServiceInfo` dipakai bersama pemilih model dan form.
  - Agent dasar dikunci saat edit, model "Service default" = `null`, skill di luar katalog tetap
    tampil supaya bisa dilepas.
  - `FakeService` test menyimpan project, skill, dan thread per scope di memori.
- **Hasil ukur:** 67 test frontend, mutation check 10/10 tertangkap. Bundle 1,28 MB (388 kB gzip).
- **Pelajaran:**
  - CLI shadcn berhenti diam-diam di prompt overwrite (`label.tsx`) dengan exit 0, sehingga
    `form` dan `alert-dialog` tidak ditulis. Jalankan dengan jawaban `n` di stdin, lalu cek file.
  - Daftar yang di-mount ulang selalu fetch ulang (`staleTime` 0), jadi invalidasi hanya teruji lewat
    daftar yang tetap ter-mount (Recents). Mutation check menemukannya.
  - E2E F33 gagal di setup: `pnpm install` di build image `web` putus (`tls handshake eof`) setelah
    10 menit pemeriksaan `minimumReleaseAge` untuk 667 paket, sedangkan `BUILD_TIMEOUT_SECONDS`
    = 900. Build image `web` terpisah tanpa timeout, dari salinan `frontend/` fitur yang diuji,
    supaya pekerjaan fitur berikutnya di working tree tidak ikut masuk image. Lalu e2e dengan
    `COMPOSE_FILE="compose.yaml;<override>"` yang mengarahkan `web.build.context` ke salinan itu
    (test meneruskan `os.environ`); cache build terpakai dan 15 test lulus dalam 56 detik.

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
