"""Create thread_metadata table (F23, menggantikan tabel SQLite dari F18).

Revision ID: 0001
Revises:
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Buat tabel judul custom thread."""
    op.create_table(
        "thread_metadata",
        sa.Column("thread_id", sa.Text(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    """Hapus tabel judul custom thread."""
    op.drop_table("thread_metadata")
