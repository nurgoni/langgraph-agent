"""Definisi tabel aplikasi (SQLAlchemy Core). Alembic membandingkan migrasi dengan `METADATA`.

Tabel checkpointer LangGraph tidak didefinisikan di sini, karena dibuat dan dimigrasi oleh
`AsyncPostgresSaver.setup()`.

>>> sorted(METADATA.tables)
['projects', 'thread_metadata', 'users']
"""

from typing import Final

from sqlalchemy import CheckConstraint, Column, DateTime, Index, MetaData, Table, Text, Uuid, func
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
