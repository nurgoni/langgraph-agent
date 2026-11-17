"""Penyimpanan Project di tabel `projects` (FR-36, ADR 0004).

Repository ini tidak memeriksa hak akses. Aturan "built-in read-only" dan "project milik user lain
dianggap tidak ada" ada di layer service (`service/projects.py`).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Literal
from uuid import uuid4

from sqlalchemy import Row, case, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_service.memory.tables import projects_table

type ProjectScopeValue = Literal["builtin", "user"]
BUILTIN_SCOPE: Final[ProjectScopeValue] = "builtin"
USER_SCOPE: Final[ProjectScopeValue] = "user"
# Kolom yang boleh diubah lewat `update`. `base_agent_id`, `scope`, dan `owner_id` tetap.
UPDATABLE_COLUMNS: Final = frozenset(
    {"name", "description", "model", "instructions", "skill_ids", "settings"}
)
# Built-in lebih dulu di daftar project.
BUILTIN_SORT_RANK: Final = 0
USER_SORT_RANK: Final = 1


class UnknownProjectColumnError(ValueError):
    """`update` diminta mengubah kolom yang tidak boleh diubah."""


@dataclass(frozen=True)
class ProjectFields:
    """Isi project yang ditentukan pembuatnya (tanpa ID, pemilik, dan waktu)."""

    name: str
    base_agent_id: str
    description: str = ""
    model: str | None = None
    instructions: str = ""
    skill_ids: Sequence[str] = ()
    # Any: JSON pengaturan yang sudah divalidasi `ProjectSettings` di layer service.
    settings: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectRecord:
    """Satu baris tabel `projects`."""

    project_id: str
    owner_id: str | None
    scope: ProjectScopeValue
    name: str
    description: str
    base_agent_id: str
    model: str | None
    instructions: str
    skill_ids: tuple[str, ...]
    settings: Mapping[str, Any]  # Any: JSON pengaturan project
    created_at: datetime
    updated_at: datetime


class ProjectRepository:
    """Membuat, membaca, mengubah, dan menghapus project.

    Engine dimiliki `DatabaseEngineProvider` di lifespan.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        """Inisialisasi repository.

        Args:
            engine: Engine ke database yang sudah dimigrasi.
        """
        self._engine = engine

    async def create(self, owner_id: str, fields: ProjectFields) -> ProjectRecord:
        """Simpan project baru milik `owner_id` dengan ID UUID baru."""
        statement = (
            projects_table.insert()
            .values(project_id=str(uuid4()), owner_id=owner_id, scope=USER_SCOPE, **_values(fields))
            .returning(*projects_table.c)
        )
        return await self._write_one(statement)

    async def upsert_builtin(self, project_id: str, fields: ProjectFields) -> ProjectRecord:
        """Buat atau perbarui project built-in berdasarkan ID tetapnya (idempoten).

        Args:
            project_id: ID tetap dari katalog, misalnya `research-assistant`.
            fields: Isi project dari kode.
        """
        values = _values(fields)
        statement = insert(projects_table).values(
            project_id=project_id, owner_id=None, scope=BUILTIN_SCOPE, **values
        )
        upsert = statement.on_conflict_do_update(
            index_elements=[projects_table.c.project_id],
            set_={**values, "updated_at": func.now()},
        ).returning(*projects_table.c)
        return await self._write_one(upsert)

    async def get(self, project_id: str) -> ProjectRecord | None:
        """Project dengan ID ini, tanpa memeriksa pemiliknya."""
        query = select(*projects_table.c).where(projects_table.c.project_id == project_id)
        async with self._engine.connect() as connection:
            row = (await connection.execute(query)).first()
        return None if row is None else _record(row)

    async def list_visible(self, owner_id: str) -> list[ProjectRecord]:
        """Project built-in (urut nama) dan milik `owner_id` (terbaru diubah dulu).

        Built-in diurutkan berdasarkan nama, bukan `updated_at`, karena semuanya di-upsert ulang
        setiap startup dan urutan waktunya tidak bermakna.
        """
        is_builtin = projects_table.c.scope == BUILTIN_SCOPE
        scope_rank = case((is_builtin, BUILTIN_SORT_RANK), else_=USER_SORT_RANK)
        builtin_name = case((is_builtin, projects_table.c.name), else_=None)
        query = (
            select(*projects_table.c)
            .where(
                or_(
                    projects_table.c.scope == BUILTIN_SCOPE,
                    projects_table.c.owner_id == owner_id,
                )
            )
            .order_by(scope_rank, builtin_name, projects_table.c.updated_at.desc())
        )
        async with self._engine.connect() as connection:
            rows = (await connection.execute(query)).all()
        return [_record(row) for row in rows]

    async def update(
        self,
        project_id: str,
        changes: Mapping[str, Any],  # Any: nilai kolom yang sudah divalidasi schema
    ) -> ProjectRecord | None:
        """Ubah kolom tertentu dan perbarui `updated_at`.

        Returns:
            Project setelah diubah, atau `None` jika ID tidak ada.

        Raises:
            UnknownProjectColumnError: Jika `changes` berisi kolom yang tidak boleh diubah.
        """
        unknown = sorted(set(changes) - UPDATABLE_COLUMNS)
        if unknown:
            raise UnknownProjectColumnError(f"Project columns cannot be updated: {unknown}")
        values: dict[str, Any] = dict(changes)  # Any: nilai kolom
        if "skill_ids" in values:
            values["skill_ids"] = list(values["skill_ids"])
        statement = (
            projects_table.update()
            .where(projects_table.c.project_id == project_id)
            .values(**values, updated_at=func.now())
            .returning(*projects_table.c)
        )
        async with self._engine.begin() as connection:
            row = (await connection.execute(statement)).first()
        return None if row is None else _record(row)

    async def delete(self, project_id: str) -> bool:
        """Hapus project. Thread di dalamnya dihapus oleh layer service lebih dulu.

        Returns:
            `True` jika ada baris yang terhapus.
        """
        statement = delete(projects_table).where(projects_table.c.project_id == project_id)
        async with self._engine.begin() as connection:
            result = await connection.execute(statement)
        return result.rowcount > 0

    async def _write_one(self, statement: Any) -> ProjectRecord:  # Any: statement SQLAlchemy
        """Jalankan insert/upsert dengan `RETURNING` dan kembalikan barisnya."""
        async with self._engine.begin() as connection:
            row = (await connection.execute(statement)).one()
        return _record(row)


def _values(fields: ProjectFields) -> dict[str, Any]:  # Any: nilai kolom
    """Nilai kolom dari `ProjectFields`, dengan koleksi diubah ke tipe JSON."""
    return {
        "name": fields.name,
        "description": fields.description,
        "base_agent_id": fields.base_agent_id,
        "model": fields.model,
        "instructions": fields.instructions,
        "skill_ids": list(fields.skill_ids),
        "settings": dict(fields.settings),
    }


def _record(row: Row[*tuple[Any, ...]]) -> ProjectRecord:  # Any: baris hasil query
    """Ubah baris tabel menjadi `ProjectRecord`."""
    return ProjectRecord(
        project_id=row.project_id,
        owner_id=row.owner_id,
        scope=BUILTIN_SCOPE if row.scope == BUILTIN_SCOPE else USER_SCOPE,
        name=row.name,
        description=row.description,
        base_agent_id=row.base_agent_id,
        model=row.model,
        instructions=row.instructions,
        skill_ids=tuple(row.skill_ids),
        settings=dict(row.settings),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
