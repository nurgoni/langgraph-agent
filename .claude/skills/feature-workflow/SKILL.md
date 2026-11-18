---
name: feature-workflow
description: Mengerjakan satu fitur ROADMAP (Fxx) dari awal sampai siap di-commit di repo ini, yaitu klarifikasi Langkah 1, desain, implementasi dan test, verifikasi (cek, mutation check, smoke test model asli, e2e), dokumentasi, lalu daftar command git. Pakai saat user meminta "lanjut Fxx", "kerjakan fitur berikutnya", atau fitur baru dari docs/ROADMAP.md.
---

# Feature workflow

Satu fitur ROADMAP = satu branch `feature/Fxx-<slug>`. Aturan kode ada di `AGENTS.md`. Skill ini
mengatur **urutan kerja** di sekitarnya.

## 0. Konteks

- Jika user bilang command git fitur sebelumnya sudah dieksekusi, anggap fitur itu sudah di-merge.
  Jangan memeriksanya dengan git.
- Baca bagian fitur di `docs/ROADMAP.md` (File, Langkah 1, Catatan desain, Rencana commit,
  Acceptance), FR terkait di `PRD.md`, ADR yang dirujuk, dan `.agents/memory.md`.
- Baca kode yang akan disentuh sebelum mendesain. Grep pemanggil setiap function yang
  signature-nya akan berubah.

## 1. Langkah 1: klarifikasi

- Kumpulkan keputusan yang ambigu: pertanyaan di ROADMAP § Langkah 1, open question di PRD §11,
  dan pilihan yang mengubah scope atau kontrak API.
- Tanyakan dengan `AskUserQuestion` (maksimal 4 pertanyaan per panggilan). Opsi pertama adalah
  rekomendasi, diberi label "(Recommended)", dan setiap opsi menjelaskan konsekuensinya. Jangan
  bertanya hal yang bisa diputuskan dari kode atau konvensi; putuskan sendiri lalu laporkan.
- Kirim satu kalimat status sebelum bertanya. Dialog pertanyaan menutupi teks lain.

## 2. Probe sebelum mendesain

Perilaku library yang belum pasti (urutan hasil, interrupt, callback, format provider) dicek
dengan script kecil di scratchpad, bukan ditebak. Contoh yang pernah mengubah desain:
`interrupt()` di `ToolNode` (F30), dan urutan `InMemoryStore.asearch` (F30). Untuk database,
buat database sementara (lihat `references/smoke_template.py`).

## 3. Implementasi

- Ikuti prosedur 5 langkah dan batas layer di `AGENTS.md`. Docstring berbahasa Indonesia.
  Docstring `@tool` dan prompt berbahasa Inggris.
- Edit besar lewat script Python di scratchpad atau tool Edit, bukan heredoc panjang (lihat
  memory.md § Pelajaran Lintas Fitur).
- API berubah → `uv run python -m agent_service.export_contracts`.
- Migrasi baru → revisi Alembic + `expected_heads()` doctest + `KEPT_TABLES` jika ada tabel
  migrasi baru.

## 4. Test

- Mirror `src/`. DB lewat fixture `database_url`, LLM lewat `FakeModel`, endpoint lewat
  `ASGITransport` + lifespan (`tests/service/conftest.py`). Tanpa network.
- Acceptance criteria ROADMAP masing-masing punya test yang menyebutnya.
- Isolasi data (NFR-9) dites per resource baru: user lain → 404.

## 5. Verifikasi

Jalankan berurutan. Semua harus hijau sebelum lanjut:

```bash
uv run ruff check . && uv run ruff format --check . && uv run pyrefly check \
  && uv run python -m agent_service.export_contracts --check && uv run pytest -q
```

- **Mutation check** untuk logika inti (otorisasi, isolasi, idempotensi, wiring): patahkan satu
  baris lewat Edit atau `sed`, jalankan test terkait, pastikan gagal, lalu kembalikan dan buktikan
  baris aslinya kembali (`grep -c`). Jangan saat e2e Docker sedang build.
- **E2E Docker** di background: `uv run pytest -q -m integration tests/integration`. Tambah test
  e2e jika fitur menyentuh migrasi, image, atau CLI.
- **Smoke test model asli** jika fitur menyentuh perilaku model: salin
  `references/smoke_template.py` ke scratchpad, sesuaikan skenarionya, dan jalankan di database
  sementara. Cek dulu Ollama (`curl -s http://127.0.0.1:11434/api/tags`). Catat hasil ukur.
- Jumlah suppression pyrefly (`INFO 0 errors (N suppressed)`) tidak boleh naik tanpa alasan.

## 6. Dokumentasi (Definition of Done)

- `docs/ROADMAP.md`: status `done`, § Langkah 1 (keputusan user), § Penyesuaian saat
  implementasi, acceptance dicentang dengan bukti singkat.
- `PRD.md` jika requirement berubah (FR, tabel endpoint, §11 open question terjawab).
- `CHANGELOG.md` § [Unreleased]: Added/Changed, termasuk langkah upgrade (migrasi, env baru).
- `README.md` dan `.env.example` untuk command, env var, dan endpoint baru. `AGENTS.md` § Perintah
  untuk entrypoint baru. `docs/ARCHITECTURE.md` untuk alur dan desain.
- `.agents/memory.md` lewat skill `memory-maintenance`.

## 7. Laporan ke user

Dalam Bahasa Indonesia:
1. Keputusan user dan cara penerapannya.
2. Keputusan yang diambil sendiri beserta alasannya.
3. Verifikasi: hasil cek, jumlah test, e2e, mutation check, dan smoke test (angka asli).
4. Hal yang harus user lakukan sebelum menjalankan service (`uv sync`, `run_migrate`, `.env`).
5. Daftar command git (skill `git-handoff`), lalu fitur berikutnya.
