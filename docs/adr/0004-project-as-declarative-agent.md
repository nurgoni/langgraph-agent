# 0004: Project sebagai agent deklaratif

- **Status:** Accepted
- **Tanggal:** 2026-11-15
- **Fitur terkait:** F26, F34, F40, F45

## Konteks

Produk chat AI (Microsoft 365 Copilot Agent Builder, Custom GPTs, Claude Projects) memakai pola yang
sama: agent adalah **konfigurasi** (instruksi, knowledge, kemampuan, model), bukan kode. Di v1,
setiap agent adalah class Python, dan user tidak bisa membuat variasi tanpa developer.

Layout UI yang dipilih (ADR 0003) mengikuti Claude, di mana Project mengelompokkan instruksi,
knowledge, dan chat.

## Keputusan

- **Project** adalah satu-satunya konsep "agent buatan user". Tidak ada konsep `AgentProfile`
  terpisah.

  ```text
  Project
  ├── id, name, description, owner_id, scope (builtin | user)
  ├── base_agent_id        agent kode yang dijalankan (chatbot, data-analyst, ...)
  ├── model                opsional, default model service
  ├── instructions         teks tambahan untuk system prompt
  ├── skill_ids[]          skill yang aktif
  ├── settings             max token, kebijakan persetujuan tool, dll (divalidasi)
  ├── knowledge            koleksi dokumen RAG (F43–F45)
  └── threads[]            chat milik project
  ```

- **Agent kode tetap ada** sebagai mesin (graph). Project memilih satu agent kode dan
  mengonfigurasinya. Developer menambah kemampuan baru lewat agent kode atau tool. User
  menyusunnya lewat Project.
- **Project built-in** (`scope = builtin`, read-only) di-seed saat startup, misalnya "Research
  Assistant" dan "Data Analyst". Ini yang dipakai untuk demo showcase.
- Setiap thread punya `project_id`. Kepemilikan thread tetap dicek (FR-28), ditambah akses ke
  project.
- Konfigurasi project yang memengaruhi run (instruksi, skill, model) dibaca **di awal setiap run**,
  sehingga perubahan project langsung berlaku di giliran berikutnya.

## Alternatif yang ditolak

| Alternatif | Alasan ditolak |
|---|---|
| `AgentProfile` + `Project` sebagai dua konsep | Dua hal yang hampir sama membingungkan user dan kode |
| Project murni folder (tanpa memilih agent) | Agent dengan graph khusus (interrupt, supervisor, data analyst) tidak bisa dipilih |
| Agent sepenuhnya dari konfigurasi (tanpa agent kode) | Graph khusus tidak bisa dinyatakan sebagai konfigurasi tanpa DSL baru |

## Konsekuensi

- Route lama `/{agent_id}/...` tetap dipertahankan untuk kompatibilitas. Bentuk route berbasis
  project diputuskan di Langkah 1 F26.
- `ThreadSummary` dan listing thread mendapat `project_id`.
- Fitur yang menambah "isi" agent (skill, knowledge, pengaturan tool) selalu menempel ke Project.
