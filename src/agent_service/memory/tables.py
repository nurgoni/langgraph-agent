"""Definisi tabel aplikasi (SQLAlchemy Core). Alembic membandingkan migrasi dengan `METADATA`.

Tabel checkpointer LangGraph tidak didefinisikan di sini, karena dibuat dan dimigrasi oleh
`AsyncPostgresSaver.setup()`.

>>> sorted(METADATA.tables)
['artifacts', 'projects', 'run_traces', 'thread_metadata', 'users', 'workspace_files']
"""

from typing import Final

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

METADATA: Final = MetaData()

# Judul custom thread (FR-25). Metadata checkpoint LangGraph tidak dirancang untuk diubah setelah
# ditulis, jadi judul disimpan terpisah.
thread_metadata_table: Final = Table(
    "thread_metadata",
    METADATA,
    Column("thread_id", Text, primary_key=True),
    Column("title", Text, nullable=False),
)

# Akun login (FR-33). Username disimpan huruf kecil. Password hanya disimpan sebagai hash argon2.
users_table: Final = Table(
    "users",
    METADATA,
    Column("user_id", Uuid(as_uuid=False), primary_key=True),
    Column("username", Text, nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("role", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("role IN ('user', 'service')", name="users_role_valid"),
)

# Project = agent deklaratif (FR-36, ADR 0004). `owner_id` kosong untuk project built-in, dan berisi
# `sub` token (bukan foreign key ke users, supaya service account dan akun lama tetap bisa memiliki
# project). `skill_ids` dan `settings` berupa JSON yang divalidasi schema sebelum disimpan.
projects_table: Final = Table(
    "projects",
    METADATA,
    Column("project_id", Text, primary_key=True),
    Column("owner_id", Text, nullable=True),
    Column("scope", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=False, server_default=""),
    Column("base_agent_id", Text, nullable=False),
    Column("model", Text, nullable=True),
    Column("instructions", Text, nullable=False, server_default=""),
    Column("skill_ids", JSONB, nullable=False, server_default="[]"),
    Column("settings", JSONB, nullable=False, server_default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("scope IN ('builtin', 'user')", name="projects_scope_valid"),
    CheckConstraint(
        "(scope = 'builtin') = (owner_id IS NULL)", name="projects_owner_matches_scope"
    ),
    Index("projects_owner_id_idx", "owner_id"),
)

# Trace run agent (FR-41, keputusan user F31): satu baris per span. Span `run` mewakili seluruh run
# (span_id = run_id), span `model`/`tool` adalah panggilan di dalamnya. Isi prompt dan hasil tool
# tidak disimpan, hanya nama, waktu, status, dan token.
run_traces_table: Final = Table(
    "run_traces",
    METADATA,
    Column("span_id", Uuid(as_uuid=False), primary_key=True),
    Column("run_id", Uuid(as_uuid=False), nullable=False),
    Column("owner_id", Text, nullable=False),
    Column("thread_id", Text, nullable=False),
    Column("agent_id", Text, nullable=False),
    Column("project_id", Text, nullable=True),
    Column("kind", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("ended_at", DateTime(timezone=True), nullable=False),
    Column("duration_ms", Integer, nullable=False),
    Column("input_tokens", Integer, nullable=True),
    Column("output_tokens", Integer, nullable=True),
    Column("error", Text, nullable=True),
    CheckConstraint("kind IN ('run', 'model', 'tool')", name="run_traces_kind_valid"),
    CheckConstraint("status IN ('ok', 'error', 'interrupted')", name="run_traces_status_valid"),
    Index("run_traces_run_id_idx", "run_id"),
)

# Metadata artifact (FR-46, F35). Isi file ada di `ArtifactStore` dengan kunci `storage_key`.
# `thread_id` kosong untuk upload yang belum dilampirkan; artifact ber-thread ikut terhapus saat
# thread dihapus (keputusan user F35). `owner_id` = `sub` token, seperti `projects.owner_id`.
artifacts_table: Final = Table(
    "artifacts",
    METADATA,
    Column("artifact_id", Uuid(as_uuid=False), primary_key=True),
    Column("owner_id", Text, nullable=False),
    Column("thread_id", Text, nullable=True),
    Column("name", Text, nullable=False),
    Column("mime_type", Text, nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("storage_key", Text, nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("size_bytes >= 0", name="artifacts_size_not_negative"),
    Index("artifacts_owner_id_idx", "owner_id"),
    Index("artifacts_thread_id_idx", "thread_id"),
)

# Workspace per thread (FR-47, F36): satu baris per file, isi sebagai bytes. Kepemilikan ikut
# thread (diperiksa service sebelum run), dan semua file ikut terhapus saat thread dihapus.
workspace_files_table: Final = Table(
    "workspace_files",
    METADATA,
    Column("thread_id", Text, nullable=False),
    Column("path", Text, nullable=False),
    Column("content", LargeBinary, nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    PrimaryKeyConstraint("thread_id", "path", name="workspace_files_pkey"),
)
