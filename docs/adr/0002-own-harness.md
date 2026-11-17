# 0002: Lapisan harness dibangun sendiri di atas LangGraph

- **Status:** Accepted
- **Tanggal:** 2026-11-15
- **Fitur terkait:** F27–F30, F36, F37

## Konteks

Agent v1 punya system prompt yang di-hard-code di Python, tanpa skill, tanpa long-term memory, dan
tanpa context management. Harness modern (Claude Code, Hermes) merakit prompt setiap giliran dari
banyak sumber: instruksi, daftar skill, memory, file workspace, dan riwayat yang dipangkas.

Ada library yang sudah menyediakan ini di atas LangGraph (`deepagents`, middleware `create_agent`
LangChain v1). Keduanya belum dievaluasi, perilakunya berubah cepat, dan asumsinya condong ke
single-user, sedangkan service ini multi-user.

## Keputusan

Harness ditulis sendiri sebagai package `harness/`, tanpa dependency ke `deepagents` atau package
`langchain`. Komponennya:

| Komponen | Tanggung jawab | Fitur |
|---|---|---|
| `ContextBuilder` | Merakit system prompt setiap giliran dari bagian-bagian berurutan dan berbatas ukuran | F27 |
| `SkillRegistry` + tool `load_skill` | Discovery dan progressive disclosure skill | F28 |
| `ContextPolicy` | Memangkas/meringkas riwayat sesuai anggaran token | F29 |
| `MemoryToolkit` + tool memory | Long-term memory per user dengan persetujuan | F30 |
| `Workspace` + file tools | Virtual filesystem per thread, offloading output tool besar | F36 |
| `Sandbox` + tool eksekusi | Menjalankan kode di lingkungan terisolasi | F37 |

Pola dari library lain boleh **ditiru** (desain), tetapi kodenya tidak di-import.

## Alternatif yang ditolak

| Alternatif | Alasan ditolak |
|---|---|
| Adopsi `deepagents` | Belum ada waktu untuk meriset perilakunya. Isolasi multi-user harus ditambal |
| Middleware `create_agent` LangChain v1 | Menambah dependency `langchain`. Graph yang sudah ada (closure di `build()`) harus ditulis ulang |

## Konsekuensi

- Kontrol penuh atas isolasi user, keamanan, dan test (`FakeModel`, fake per abstraksi).
- Waktu pengembangan lebih panjang. Fitur seperti summarization harus ditulis dan dites sendiri.
- Harness dipakai lewat komposisi oleh agent (`ToolCallingAgent` menerima `ContextBuilder` dan
  daftar tool harness), bukan lewat base class baru, supaya agent v1 tetap berjalan tanpa harness.
- Jika suatu saat ingin beralih ke library, batasnya jelas: package `harness/`.
