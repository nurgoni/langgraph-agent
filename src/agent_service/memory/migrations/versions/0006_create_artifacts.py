"""Create artifacts table (F35, metadata file artifact).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Buat tabel metadata artifact beserta index pemilik dan thread."""
    op.create_table(
        "artifacts",
        sa.Column("artifact_id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("thread_id", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("size_bytes >= 0", name="artifacts_size_not_negative"),
    )
    op.create_index("artifacts_owner_id_idx", "artifacts", ["owner_id"])
    op.create_index("artifacts_thread_id_idx", "artifacts", ["thread_id"])


def downgrade() -> None:
    """Hapus tabel artifact. File di `ArtifactStore` tidak ikut dihapus."""
    op.drop_index("artifacts_thread_id_idx", table_name="artifacts")
    op.drop_index("artifacts_owner_id_idx", table_name="artifacts")
    op.drop_table("artifacts")
