---
name: git-handoff
description: Menyusun daftar command git yang dijalankan user (agent tidak pernah menjalankan git di repo ini). Pakai setiap kali pekerjaan siap di-commit, di-push, di-PR, atau di-merge, termasuk di akhir feature-workflow dan release.
---

# Git handoff

Aturan user (F21, `.agents/memory.md` § Aturan Kerja): **semua command git dijalankan user**.
Agent hanya menulis daftar command yang akan dieksekusi.

## Larangan

- Jangan menjalankan `git` dalam bentuk apa pun, termasuk `git status`, `git diff`, `git log`, dan
  `git diff --stat` di dalam rangkaian perintah verifikasi. Classifier menolaknya.
- Jangan menebak isi working tree dari git. Daftar file diambil dari file yang memang diubah atau
  dibuat di sesi ini.
- Jangan memakai `--no-verify`, force-push ke `main`/`develop`, atau commit langsung ke branch
  permanen (CONTRIBUTING.md).

## Menyusun daftar command

Tulis untuk PowerShell (shell user), dalam satu blok berurutan:

1. **Branch** dari `develop` terbaru: `git checkout develop`, `git pull origin develop`, lalu
   `git checkout -b <branch>`. Nama: `feature/Fxx-<slug>` (ROADMAP), `chore/<slug>`, `fix/<slug>`,
   `docs/<slug>`, `release/vX.Y.Z`.
2. **Commit per Rencana commit** milik fitur di `docs/ROADMAP.md`. Commit yang digabung atau
   dipisah dicatat di ROADMAP § Penyesuaian saat implementasi. Setiap commit harus lolos hook:
   test ikut di commit yang sama dengan kode yang dites, dan `contracts/` ikut di commit yang
   mengubah API.
3. **`git add` dengan path eksplisit.** Folder boleh dipakai jika semua isinya milik commit itu.
4. **File untracked milik commit berikutnya.** Hook pyrefly memeriksa file untracked, sedangkan
   perubahan yang belum di-stage disimpan sementara. Jika file untracked meng-import perubahan
   yang belum di-stage, singkirkan dulu lalu kembalikan setelah commit:

   ```powershell
   $t = "$env:TEMP\fxx"; New-Item -ItemType Directory -Force $t | Out-Null
   Move-Item tests\agents\test_new.py $t\test_new.py
   # ... git add + git commit ...
   Move-Item $t\test_new.py tests\agents\test_new.py
   ```

   Beri nama tujuan yang unik jika dua file bernama sama (`harness_memory.py`). Lewati langkah ini
   jika file untracked hanya meng-import kode yang sudah di-stage.
5. **Pesan commit:** Conventional Commits berbahasa Inggris, subject ≤ 72 karakter, imperatif,
   huruf kecil, tanpa titik. Pakai beberapa `-m`: subject, body (*kenapa*), `Refs: Fxx` (fitur
   roadmap saja), lalu trailer atribusi dari harness jika ada (`Co-Authored-By: ...`).
6. `git status`, lalu `git push -u origin <branch>`. Hook pre-push menjalankan pytest, jadi
   ingatkan bahwa Docker Postgres harus menyala.
7. **PR lewat web** (CLI `gh` tidak terpasang). Branch fitur: PR ke `develop`, judul = squash title
   dari ROADMAP, **squash merge**. Ingatkan user memeriksa judul commit di dialog squash sebelum
   konfirmasi: tanpa default "Pull request title", GitHub memakai nama branch (#45) atau judul PR
   lama (#40). Release: lihat skill `release` (merge commit, bukan squash).
8. **Setelah merge**, hapus branch lokal dan remote:

   ```powershell
   git checkout develop
   git pull origin develop
   git branch -D <branch>
   git push origin --delete <branch>
   ```

   `-D` diperlukan karena setelah squash merge git tidak mengenali branch sebagai sudah di-merge.

Tutup dengan: "Jika `git status` setelah commit terakhir masih menunjukkan file yang berubah,
kirimkan hasilnya." Saat user melaporkan "semua command git sudah dieksekusi", anggap branch
sudah di-merge dan dihapus.
