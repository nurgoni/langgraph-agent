---
name: release
description: Menyiapkan rilis milestone vX.Y.Z di repo ini, yaitu bump versi, CHANGELOG dengan catatan upgrade, uv.lock, kontrak API, verifikasi, lalu daftar command release → main → tag → back-merge untuk dijalankan user. Pakai saat user meminta "siapkan rilis", atau setelah fitur terakhir sebuah milestone di-merge.
---

# Release

Proses resmi ada di `CONTRIBUTING.md` § Release. Versi per milestone ada di `docs/ROADMAP.md`
§ Milestone & Rilis (M5 → `v0.5.0`, M6 → `v0.6.0`, dan seterusnya). Di branch release hanya boleh
ada bump versi, changelog, dan perbaikan bug kecil.

## Menyiapkan file (agent)

Perubahan dibuat di working tree `develop`. Saat user membuat branch release, perubahan ikut
pindah.

1. `pyproject.toml`: `version = "X.Y.Z"`.
2. `CHANGELOG.md`:
   - Sisipkan `## [X.Y.Z] - YYYY-MM-DD` di bawah `## [Unreleased]`, sehingga `[Unreleased]`
     kosong.
   - Satu paragraf ringkasan milestone, lalu **Catatan upgrade** bernomor: `uv sync` (extra baru),
     `run_migrate` (revisi baru), env var baru/wajib, perubahan signature untuk agent custom, dan
     perubahan kontrak API yang breaking.
   - Rapikan entri: hapus label "belum dirilis", gabungkan duplikat, dan hapus baris kosong yang
     tersesat. Sesuatu bukan breaking jika fiturnya baru muncul di rilis yang sama.
   - Link di bawah: `[Unreleased]` membandingkan `vX.Y.Z...HEAD`, ditambah baris
     `[X.Y.Z]: .../compare/v<sebelumnya>...vX.Y.Z`.
3. `uv lock --offline`, lalu `uv sync`.
4. `uv run python -m agent_service.export_contracts` (`info.version` ikut versi package). Pastikan
   `"version": "X.Y.Z"` ada di `contracts/openapi.json`.
5. `.agents/memory.md` § Status: rilis disiapkan, dan fitur berikutnya.
6. Verifikasi: ruff check, ruff format --check, pyrefly, `export_contracts --check`, dan pytest.
   E2E Docker cukup dari fitur terakhir, kecuali ada perubahan selain versi.

## Daftar command (user, lewat skill `git-handoff`)

```powershell
# 1. Branch release (perubahan yang belum di-commit ikut pindah)
git switch develop
git pull origin develop
git switch -c release/vX.Y.Z

# 2. Commit
git add pyproject.toml uv.lock CHANGELOG.md contracts/openapi.json .agents/memory.md
git commit -m "chore(release): prepare vX.Y.Z" -m "<trailer atribusi>"
git status
git push -u origin release/vX.Y.Z
```

3. PR `release/vX.Y.Z` → `main` lewat web, judul `chore(release): vX.Y.Z`, merge dengan **"Create a
   merge commit"** (bukan squash). Ingatkan user memeriksa tombol merge: jika ruleset `main`
   belum dipasang (CONTRIBUTING § Setup Awal Repo), tombol default GitHub bisa "Squash and merge"
   (insiden v0.7.0).

Lanjut ke langkah 4 hanya jika PR berstatus **Merged**. Tanpa itu, tag menunjuk ke rilis lama
(insiden v0.6.0, lihat memory.md).

```powershell
# 4. Tag di main (log teratas harus merge PR release/vX.Y.Z)
git switch main
git pull origin main
git log --oneline -3
git tag -a vX.Y.Z -m "vX.Y.Z: <nama milestone>"
git push origin vX.Y.Z

# 5. Back-merge ke develop, lalu hapus branch release
git switch develop
git pull origin develop
git merge --no-ff main -m "chore(release): merge vX.Y.Z back into develop"
git push origin develop
git branch -d release/vX.Y.Z
git push origin --delete release/vX.Y.Z
```

Setelah rilis: sebutkan fitur pertama milestone berikutnya beserta pertanyaan Langkah 1-nya. Jika
memory.md melewati ±300 baris, jalankan skill `memory-maintenance` (arsip milestone yang baru
dirilis).

## Jika release terlanjur di-squash

Gejala: back-merge (langkah 5) konflik di `CHANGELOG.md` dan `.agents/memory.md`, dan `git log main`
menampilkan `chore(release): vX.Y.Z (#NN)` tanpa merge commit. Ikuti CONTRIBUTING.md § Release
("Jika release terlanjur di-squash"): pastikan `git diff --stat release/vX.Y.Z main` kosong,
ambil versi `main` (`git checkout --theirs`), pastikan `git diff --cached --stat main` kosong, lalu
commit back-merge. Jangan force-push `main`.
