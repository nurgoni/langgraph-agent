"""Mark the long-term memory store (F30).

Tabel store (`store`, `store_migrations`) dibuat oleh `AsyncPostgresStore.setup()` di
`upgrade_database`, sebelum Alembic. Revisi ini tidak mengubah skema. Ia ada supaya database yang
sudah di revisi 0003 ditolak `ensure_database_migrated` sampai migrasi dijalankan lagi, sehingga
tabel store pasti ada sebelum service start.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17
"""

from collections.abc import Sequence

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Tidak ada perubahan skema Alembic (lihat docstring modul)."""


def downgrade() -> None:
    """Tidak ada perubahan skema Alembic. Tabel store dikelola LangGraph."""
