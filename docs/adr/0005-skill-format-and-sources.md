# 0005: Format skill `SKILL.md` dan sumber skill bertingkat

- **Status:** Accepted
- **Tanggal:** 2026-11-15
- **Fitur terkait:** F28, F36, F37, F40, backlog B1

## Konteks

Skill adalah pengetahuan prosedural (instruksi + file pendukung) yang dimuat model hanya saat
relevan (progressive disclosure). Skill tidak menambah kemampuan. Kemampuan tetap datang dari tool.
Untuk showcase, skill built-in di repo sudah cukup. Skill yang dibuat lewat UI menjadi fitur
tambahan, dan desain awal harus bisa menerimanya tanpa refactor.

## Keputusan

**Format.** Mengikuti spesifikasi terbuka Agent Skills (agentskills.io): satu folder per skill dengan
`SKILL.md` berisi frontmatter YAML (`name` ≤ 64 karakter, `description` ≤ 1024 karakter) dan isi
Markdown. File pendukung (`references/`, `scripts/`, `assets/`) dirujuk satu tingkat dari
`SKILL.md`. Skill yang ditulis untuk ekosistem lain bisa diimpor tanpa konversi.

**Model data** (sama untuk semua sumber):

```text
Skill { id, name, description, body, resources[], version, scope, owner_id?, read_only }
scope: builtin | org | user | project
id   : "<scope>/<name>"  (contoh "builtin/sales-metrics")
```

**Sumber bertingkat.** `SkillRegistry` menggabungkan satu atau lebih `SkillSource`:

| Sumber | Kapan | Isi |
|---|---|---|
| `FilesystemSkillSource` | F28 | `src/agent_service/skills/builtin/<name>/SKILL.md`, ikut versi git dan review PR. `scope = builtin`, `read_only = true` |
| `DatabaseSkillSource` | Backlog B1 | Tabel `skills` + resource di artifact storage. Dibuat lewat API/UI |

**Alur di runtime:**

1. Startup: registry memuat dan **memvalidasi** semua skill. Skill yang tidak valid dicatat di log
   dan dilewati, tanpa menggagalkan startup.
2. Setiap giliran: `ContextBuilder` menyisipkan **indeks** (nama + deskripsi) dari skill yang aktif
   di Project.
3. Model memanggil tool `load_skill(name)` untuk isi lengkap, dan `load_skill(name, path)` untuk
   file referensi. Tool hanya bisa memuat skill yang aktif di Project.
4. Script di skill hanya bisa dijalankan setelah sandbox ada (F37), dan selalu di dalam sandbox.

**API.** F28 hanya menyediakan `GET /skills` dan `GET /skills/{id}` (read-only). `POST`, `PATCH`, dan
`DELETE` ditambahkan di B1 dengan validator yang sama.

## Alternatif yang ditolak

| Alternatif | Alasan ditolak |
|---|---|
| Semua skill langsung disisipkan ke prompt | Prompt membengkak, dan model kecil (9B) kewalahan |
| Pemilihan skill dengan vector search | Pemilihan oleh model dari deskripsi sudah menjadi praktik standar. Search baru perlu jika jumlah skill sangat besar |
| Format skill buatan sendiri | Tidak bisa memakai skill dari ekosistem lain |

## Konsekuensi

- Kualitas `description` menentukan apakah skill terpakai. Deskripsi ikut dites di eval (F31).
- Skill dari UI (B1) hanya menambah `DatabaseSkillSource`, endpoint tulis, dan editor. Model data,
  tool, dan `ContextBuilder` tidak berubah.
- Semantic layer data analyst (definisi metrik, kamus kolom) ditulis sebagai skill built-in (F40).
