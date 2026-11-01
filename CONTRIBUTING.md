# CONTRIBUTING

Panduan git lifecycle untuk project ini: branch, commit, pull request, release, dan hotfix.
Aturan penulisan kode ada di [AGENTS.md](AGENTS.md). Daftar fitur dan urutan pengerjaannya ada di
[docs/ROADMAP.md](docs/ROADMAP.md).

## Ringkasan

```text
feature/Fxx-*  ──squash──►  develop  ──release/vX.Y.Z (--no-ff)──►  main  (tag vX.Y.Z)
                               ▲                                       │
                               └──────────── back-merge ───────────────┘
hotfix/vX.Y.Z-*  ◄── main ──► main (tag) + back-merge ke develop
```

- Strategi branch adalah **Git Flow ringan**: dua branch permanen dan branch sementara berumur
  pendek.
- **Feature → develop: squash merge.** Satu fitur menjadi satu commit rapi di develop.
- **Release/hotfix → main: merge commit (`--no-ff`)**, lalu diberi tag.
- **Commit message: Conventional Commits, dalam bahasa Inggris.** Dokumentasi tetap berbahasa
  Indonesia.

## Branch

### Branch permanen

| Branch | Isi | Aturan |
|---|---|---|
| `main` | Kode yang sudah dirilis | Protected. Hanya menerima merge dari `release/*` dan `hotfix/*`. Setiap merge diberi tag. |
| `develop` | Integrasi fitur, default branch | Protected. Hanya menerima PR dengan CI hijau. |

### Branch sementara

Format: huruf kecil, kebab-case, ≤ ~50 karakter, dan diawali prefix.

| Prefix | Dibuat dari | Merge ke | Contoh |
|---|---|---|---|
| `feature/Fxx-<slug>` | `develop` | `develop` (squash) | `feature/F08-sse-streaming` |
| `fix/<slug>` | `develop` | `develop` (squash) | `fix/stream-done-on-error` |
| `refactor/<slug>` | `develop` | `develop` (squash) | `refactor/split-stream-handlers` |
| `docs/<slug>` | `develop` | `develop` (squash) | `docs/update-env-table` |
| `chore/<slug>` | `develop` | `develop` (squash) | `chore/bump-langgraph` |
| `release/vX.Y.Z` | `develop` | `main` (`--no-ff`) + back-merge ke `develop` | `release/v0.1.0` |
| `hotfix/vX.Y.Z-<slug>` | `main` | `main` (`--no-ff`) + back-merge ke `develop` | `hotfix/v0.1.1-auth-header` |

- `Fxx` mengacu ke ID fitur di [ROADMAP](docs/ROADMAP.md). Pekerjaan di luar roadmap memakai
  prefix `fix/`, `chore/`, dan seterusnya tanpa ID.
- Branch hidup sesingkat mungkin (target < 3 hari). Rebase ke `develop` terbaru sebelum membuka PR:

  ```bash
  git fetch origin
  git rebase origin/develop
  ```

## Commit Message

Mengikuti [Conventional Commits](https://www.conventionalcommits.org/), dalam bahasa Inggris.

```text
<type>(<scope>): <subject>

<body: jelaskan KENAPA, bukan apa; wrap di 72 karakter>

<footer: Refs, BREAKING CHANGE, Co-Authored-By>
```

### Type

| Type | Kapan |
|---|---|
| `feat` | Kemampuan baru bagi pengguna/API |
| `fix` | Perbaikan bug |
| `refactor` | Perubahan struktur tanpa mengubah perilaku |
| `perf` | Optimasi performa (sertakan angka di body) |
| `test` | Menambah/memperbaiki test saja |
| `docs` | Dokumentasi saja |
| `build` | Dependency, packaging, Docker |
| `ci` | Workflow CI |
| `chore` | Pemeliharaan lain (config, rilis) |
| `style` | Format saja, tanpa perubahan logika |
| `revert` | Membatalkan commit sebelumnya |

### Scope

Sesuai layer: `core`, `llm`, `memory`, `schema`, `agents`, `service`, `client`, `ui`, `docker`, `ci`,
`release`. Untuk perubahan di `.agents/memory.md` gunakan `memory-md` agar tidak tertukar dengan
layer `memory`. Scope boleh dikosongkan untuk perubahan lintas layer (contoh `docs: ...`).

### Aturan subject

- Mode imperatif: "add", "fix", "remove", bukan "added" atau "adds". Uji dengan kalimat: *"If
  applied, this commit will \<subject\>"*.
- Huruf kecil di awal, tanpa titik di akhir, ≤ 72 karakter termasuk prefix.
- Menjelaskan **apa** yang berubah, bukan file mana yang disentuh.

### Contoh

Baik:

```text
feat(service): add StreamService handling updates and message chunks

The previous message_generator mixed four event kinds in one 110-line
function with six levels of nesting. Each event kind now has its own
private method so the done frame can be guaranteed in a single finally.

Refs: F08
```

```text
fix(service): return 404 for unknown agent id

KeyError from the registry bubbled up as a 500. Map AgentNotFoundError
to 404 in the exception handler.

Refs: F06
```

```text
feat(schema)!: rename ChatMessage.type value "custom" to "event"

BREAKING CHANGE: clients must handle type "event" instead of "custom".
```

Buruk → perbaikan:

| Buruk | Masalah | Perbaikan |
|---|---|---|
| `update code` | Tidak ada type, tidak informatif | `refactor(agents): extract tool loop into ToolCallingAgent` |
| `feat: Added streaming.` | Bukan imperatif, huruf besar, ada titik | `feat(service): add sse streaming endpoint` |
| `fix stuff in service.py and client.py` | Menyebut file, gabungan dua perubahan | Pecah menjadi dua commit `fix(service): ...` dan `fix(client): ...` |
| `wip` / `fix typo` | Commit sampah di PR | Gabungkan dengan `--fixup` + autosquash |

### Commit atomik

- **Satu perubahan logis per commit.** Jika butuh kata "and" untuk dua hal yang tidak berhubungan,
  pecah menjadi dua commit.
- **Test ikut dalam commit yang sama** dengan kode yang dites (commit `test(...)` terpisah hanya
  untuk menambah coverage tanpa perubahan kode).
- **Setiap commit lolos pre-commit dan test.** Commit yang merusak build membuat `git bisect` tidak
  bisa dipakai.
- Rapikan sebelum review:

  ```bash
  git commit --fixup <sha>
  git rebase -i --autosquash origin/develop   # di terminal biasa
  ```

- Jangan pernah memakai `--no-verify`. Jika hook gagal, perbaiki penyebabnya.

### Commit oleh AI agent

Commit yang dibuat oleh coding agent mengikuti aturan yang sama, ditambah footer atribusi, misalnya:

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## Pull Request

1. **Judul = squash commit message**, dalam format Conventional + ID fitur:
   `feat(service): add sse streaming endpoint (F08)`. Squash title untuk setiap fitur sudah
   ditulis di ROADMAP.
2. **Body** mengikuti `.github/pull_request_template.md`:

   ```markdown
   ## Ringkasan
   <apa dan kenapa, 1–3 kalimat>

   ## Fitur / Requirement
   F08 · FR-7

   ## Cara Test
   uv run pytest tests/service/test_streaming.py

   ## Checklist (Definition of Done, AGENTS.md)
   - [ ] Prosedur 5 langkah + Review Mental Zen
   - [ ] ruff, pyrefly, pytest hijau
   - [ ] Contoh penggunaan (`__main__`/doctest)
   - [ ] README/PRD diperbarui jika perlu
   - [ ] `.agents/memory.md` diperbarui jika ada keputusan baru
   - [ ] Status fitur di ROADMAP diperbarui

   ## Catatan
   <keputusan desain, trade-off, follow-up>
   ```

3. **Ukuran:** idealnya < 400 baris diff (tidak termasuk lock file). Lebih besar dari itu,
   pertimbangkan untuk memecah fitur.
4. **Merge:** CI hijau + minimal 1 review (self-review terstruktur jika solo), lalu **Squash and
   merge** ke `develop` dan hapus branch.
5. Body squash commit berisi ringkasan + `Refs: Fxx`. Hapus daftar commit "fixup" bawaan GitHub.

## Release

Dilakukan di akhir setiap milestone (lihat ROADMAP: M1 → `v0.1.0`, M2 → `v0.2.0`, M3 → `v0.3.0`).

```bash
# 1. Buat branch release
git switch develop && git pull
git switch -c release/v0.1.0

# 2. Bump versi dan changelog
#    - pyproject.toml: version = "0.1.0"
#    - CHANGELOG.md: pindahkan [Unreleased] ke [0.1.0] - YYYY-MM-DD
git commit -am "chore(release): prepare v0.1.0"
git push -u origin release/v0.1.0

# 3. PR release/v0.1.0 → main, merge dengan "Create a merge commit" (--no-ff), BUKAN squash

# 4. Tag di main
git switch main && git pull
git tag -a v0.1.0 -m "v0.1.0: core + service"
git push origin v0.1.0

# 5. Back-merge ke develop, lalu hapus branch release
git switch develop
git merge --no-ff main -m "chore(release): merge v0.1.0 back into develop"
git push
git branch -d release/v0.1.0 && git push origin --delete release/v0.1.0
```

**Kenapa release tidak di-squash?** Squash membuat commit baru di `main` yang tidak dikenali oleh
`develop`. Akibatnya rilis berikutnya akan konflik dan histori kedua branch terputus. Merge
`--no-ff` menjaga keduanya tetap terhubung.

Di branch release hanya boleh ada bump versi, changelog, dan perbaikan bug kecil. Tidak boleh ada
fitur baru.

## Hotfix

```bash
git switch main && git pull
git switch -c hotfix/v0.1.1-auth-header
# perbaiki + test
git commit -m "fix(service): accept lowercase bearer scheme"
git commit -am "chore(release): prepare v0.1.1"
# PR ke main (--no-ff) → tag v0.1.1 → back-merge main ke develop (sama seperti Release langkah 4–5)
```

## Versioning

- [SemVer](https://semver.org/). Selama pre-1.0 formatnya `0.MINOR.PATCH`: MINOR naik per
  milestone, PATCH naik per hotfix.
- Tag selalu **annotated** (`git tag -a`), dengan format `vX.Y.Z`.
- `CHANGELOG.md` mengikuti [Keep a Changelog](https://keepachangelog.com/). Isi bagian
  `[Unreleased]` di setiap PR yang mengubah perilaku.

## Setup Awal Repo (sekali saja)

Bagian dari F00 di ROADMAP:

```bash
git init -b main
git add AGENTS.md PRD.md README.md CLAUDE.md CONTRIBUTING.md .agents/ docs/ .gitignore
git commit -m "docs: add project foundation documents"
git switch -c develop
git remote add origin <url>
git push -u origin main develop
```

Lalu di GitHub:

- Set `develop` sebagai default branch.
- Proteksi `main` dan `develop`: wajib PR dan status check CI, blokir force-push.
- Di `develop` aktifkan hanya "Allow squash merging". Untuk merge release ke `main` dipakai
  "Create a merge commit".

Root commit di atas adalah **satu-satunya** commit langsung ke `main`.

**Catatan:** `agent-service-toolkit/` punya repo git sendiri dan dimasukkan ke `.gitignore`. Folder
ini tetap menjadi referensi lokal, bukan submodule.

## Larangan

- Force-push ke `main` atau `develop`.
- Commit langsung ke `main` atau `develop` (kecuali root commit).
- `--no-verify`, atau melewati CI.
- Commit secret (`.env`, API key, database checkpoint `*.db`).
- Squash merge untuk `release/*` atau `hotfix/*` ke `main`.
