# 0006: Data catalog sebagai semantic layer terstruktur

- **Status:** Accepted
- **Tanggal:** 2026-11-26
- **Fitur terkait:** F39, F48, F40
- **Supersedes:** sebagian [0005](0005-skill-format-and-sources.md) (konsekuensi "semantic layer
  data analyst ditulis sebagai skill built-in")

## Konteks

Agent analisa data paling sering gagal pada pertanyaan baru bukan karena tidak bisa menulis kode,
tetapi karena **tidak mengenal datanya**: arti kolom, definisi metrik, kolom waktu yang benar, jalur
join, dan jebakan kualitas data. Rencana awal F40 menulis semua ini sebagai skill Markdown khusus
database demo (`demo-metrics`).

Cara itu punya tiga masalah:

- **Tidak bisa divalidasi.** Nama tabel atau kolom yang salah di Markdown baru ketahuan saat model
  gagal menjawab.
- **Bercampur dengan pengetahuan metode.** "Cara menganalisa tren" berlaku untuk semua data,
  sedangkan "revenue = sum(amount) dikurangi refund" hanya berlaku untuk satu data source.
- **Terikat ke satu dataset.** Setiap data source baru butuh skill baru dengan format bebas.

## Keputusan

Pengetahuan dipisah menjadi dua jenis, dengan tempat yang berbeda:

| Jenis | Contoh | Tempat | Dibaca lewat |
|---|---|---|---|
| **Pengetahuan data** | Metrik + ekspresi SQL, dimensi, grain, kolom waktu, jalur join, catatan kualitas, arti kolom | **Data catalog**: satu file YAML per data source | Tool `list_metrics`, `get_metric`, dan ringkasan di `describe_table` |
| **Pengetahuan metode** | Eksplorasi data, tren, segmentasi, root cause berbasis hipotesis, cek kualitas data, pemilihan chart | **Skill** (`SKILL.md`, ADR 0005) | `load_skill` |

Aturan data catalog:

- **Satu file per data source**, dirujuk dari registry data source (`DATA_SOURCES_FILE`). Bentuk
  final schema-nya ditetapkan di F48.
- **Divalidasi saat startup** terhadap skema database: tabel dan kolom yang dirujuk harus ada, dan
  ekspresi metrik harus bisa diparse `sqlglot`. Katalog yang tidak valid membuat data source itu
  *unavailable* dengan pesan yang jelas, tanpa menggagalkan service (pola `AgentRegistry`).
- **Opsional.** Data source tanpa katalog tetap bisa dipakai lewat primitif eksplorasi (F39).
  Katalog meningkatkan akurasi, bukan syarat.
- **Domain-agnostic.** Kode tidak mengenal nama domain apa pun. Database demo hanya fixture.
- **Bukan compiler metrik.** Ekspresi metrik adalah definisi yang dibaca model dan dipakai untuk
  verifikasi (F50), bukan SQL yang dirakit otomatis. Compiler (dbt, Cube, MetricFlow) di luar
  scope.

## Alternatif yang ditolak

| Alternatif | Alasan ditolak |
|---|---|
| Semantic layer sebagai skill Markdown (rencana awal F40) | Tidak bisa divalidasi, bercampur dengan metode, terikat dataset |
| Compiler metrik (dbt Semantic Layer, Cube, MetricFlow) | Infrastruktur besar. Kebutuhan sekarang adalah pengetahuan untuk model, bukan generator SQL |
| Kamus kolom dari `COMMENT ON COLUMN` database saja | Tidak semua database punya komentar, dan metrik serta jalur join tidak bisa dinyatakan di sana. Komentar tetap dibaca `describe_table` sebagai tambahan |

## Konsekuensi

- Skill tetap generik dan bisa dipakai lintas data source. F40 tidak lagi membuat skill
  `demo-metrics`.
- Menambah data source cukup dengan entri registry + file katalog, tanpa kode.
- Verifikasi jawaban (F50) bisa mencocokkan metrik yang dipakai model dengan definisi katalog.
- Katalog dari UI (seperti skill B1) bisa ditambahkan nanti sebagai sumber katalog baru.
