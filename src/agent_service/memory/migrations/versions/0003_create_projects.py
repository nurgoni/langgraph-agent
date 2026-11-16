"""Create projects table (F26, project sebagai agent deklaratif).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Buat tabel project beserta index pemilik."""
    op.create_table(
        "projects",
        sa.Column("project_id", sa.Text(), primary_key=True),
        sa.Column("owner_id", sa.Text(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("base_agent_id", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("skill_ids", JSONB(), nullable=False, server_default="[]"),
        sa.Column("settings", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("scope IN ('builtin', 'user')", name="projects_scope_valid"),
        sa.CheckConstraint(
            "(scope = 'builtin') = (owner_id IS NULL)", name="projects_owner_matches_scope"
        ),
    )
    op.create_index("projects_owner_id_idx", "projects", ["owner_id"])


def downgrade() -> None:
    """Hapus tabel project."""
    op.drop_index("projects_owner_id_idx", table_name="projects")
    op.drop_table("projects")
