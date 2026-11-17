"""Create run_traces table (F31, trace run agent).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Buat tabel trace beserta index per run."""
    op.create_table(
        "run_traces",
        sa.Column("span_id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("run_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint("kind IN ('run', 'model', 'tool')", name="run_traces_kind_valid"),
        sa.CheckConstraint(
            "status IN ('ok', 'error', 'interrupted')", name="run_traces_status_valid"
        ),
    )
    op.create_index("run_traces_run_id_idx", "run_traces", ["run_id"])


def downgrade() -> None:
    """Hapus tabel trace."""
    op.drop_index("run_traces_run_id_idx", table_name="run_traces")
    op.drop_table("run_traces")
