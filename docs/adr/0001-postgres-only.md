# 0001: Postgres sebagai satu-satunya database

- **Status:** Accepted
- **Tanggal:** 2026-11-15
- **Fitur terkait:** F23 (dan semua fitur M5–M10 yang menyimpan data)

## Konteks

v1 memakai satu file SQLite (`AsyncSqliteSaver` + tabel `thread_metadata` lewat `aiosqlite`). Fase 2
menambah kebutuhan yang tidak bisa dipenuhi SQLite dengan baik:

- **Banyak proses menulis bersamaan.** Worker scheduler (F41) dan ingestion (F43) berjalan sebagai
  proses terpisah dari API. SQLite hanya mengizinkan satu penulis, sehingga muncul
  `database is locked`.
- **Vector search** untuk RAG (F44). Postgres punya `pgvector` di database yang sama.
- **Lock antar proses** untuk mencegah job terjadwal berjalan dobel (advisory lock).
- **Tabel aplikasi bertambah banyak** (users, projects, skills, artifacts, workspace, jobs,
  documents) dan butuh migrasi skema yang tercatat.

## Keputusan

- Postgres menjadi **satu-satunya** database service. SQLite dihapus dari jalur runtime.
- Postgres berjalan sebagai service di `compose.yaml` (image dengan `pgvector`), dengan volume
  sendiri dan healthcheck. Dev lokal, CI e2e, dan demo memakai compose yang sama.
- Checkpointer: `AsyncPostgresSaver` (`langgraph-checkpoint-postgres`) dengan connection pool
  `psycopg`. Long-term memory memakai `AsyncPostgresStore`.
- Tabel aplikasi: SQLAlchemy Core (async) + **Alembic** untuk migrasi. Migrasi dijalankan oleh
  service compose `migrate` (sekali jalan) sebelum service API dan worker start, bukan otomatis
  di lifespan.
- Konfigurasi lewat satu env var `DATABASE_URL`. `SQLITE_DB_PATH` dihapus.
- Test yang menyentuh database berjalan ke Postgres di loopback (container lokal atau service CI).
  Fixture `block_network` sudah mengizinkan loopback.

## Alternatif yang ditolak

| Alternatif | Alasan ditolak |
|---|---|
| Tetap SQLite + tambah Postgres (dua backend) | Matriks test berlipat dua. Fitur inti fase 2 (pgvector, worker, lock) tetap hanya jalan di Postgres |
| SQLite + vector DB terpisah (Chroma) | Dua penyimpanan untuk satu domain. ACL dan transaksi tidak bisa digabung |
| ORM penuh (SQLAlchemy ORM / SQLModel) | Core sudah cukup untuk repository yang eksplisit, dan tidak ada lazy loading tersembunyi |
| Migrasi otomatis di lifespan | Beberapa replika atau worker bisa menjalankan migrasi bersamaan |

## Konsekuensi

- Menjalankan service sekarang **wajib** Postgres. `uv run python -m agent_service.run_service`
  tanpa compose butuh `DATABASE_URL` yang valid.
- Unit test yang butuh database menjadi lebih lambat dan butuh Docker atau Postgres lokal. Test
  murni (agent dengan `FakeModel` + `InMemorySaver`) tetap tanpa database.
- Data thread di `checkpoints.db` lama tidak dimigrasi (hanya data dev).
- `CheckpointerProvider` dan `ThreadMetadataRepository` ditulis ulang. Kontrak publiknya (async
  context manager, repository per tabel) dipertahankan.
