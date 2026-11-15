"""Definisi tabel aplikasi (SQLAlchemy Core). Alembic membandingkan migrasi dengan `METADATA`.

Tabel checkpointer LangGraph tidak didefinisikan di sini, karena dibuat dan dimigrasi oleh
`AsyncPostgresSaver.setup()`.

>>> sorted(METADATA.tables)
['thread_metadata']
"""

from typing import Final

from sqlalchemy import Column, MetaData, Table, Text

METADATA: Final = MetaData()

# Judul custom thread (FR-25). Metadata checkpoint LangGraph tidak dirancang untuk diubah setelah
# ditulis, jadi judul disimpan terpisah.
thread_metadata_table: Final = Table(
    "thread_metadata",
    METADATA,
    Column("thread_id", Text, primary_key=True),
    Column("title", Text, nullable=False),
)
