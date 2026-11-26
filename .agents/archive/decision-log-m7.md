# Decision Log M7 (arsip)

Dipindah utuh dari `.agents/memory.md` pada 2026-11-26 (skill `memory-maintenance`), setelah
v0.7.0 (M7 Files & Execution) dirilis. Entri terbaru di atas. Pelajaran yang masih berlaku
diringkas di memory.md § Pelajaran Lintas Fitur.

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
