"""Create workspace_files table (F36, workspace per thread).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Buat tabel file workspace dengan kunci (thread, path)."""
    op.create_table(
        "workspace_files",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("thread_id", "path", name="workspace_files_pkey"),
    )


def downgrade() -> None:
    """Hapus tabel file workspace."""
    op.drop_table("workspace_files")
