"""Definisi tabel aplikasi (SQLAlchemy Core). Alembic membandingkan migrasi dengan `METADATA`.

Tabel checkpointer LangGraph tidak didefinisikan di sini, karena dibuat dan dimigrasi oleh
`AsyncPostgresSaver.setup()`.

>>> sorted(METADATA.tables)
['thread_metadata', 'users']
"""

from typing import Final

from sqlalchemy import CheckConstraint, Column, DateTime, MetaData, Table, Text, Uuid, func

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
