"""DatabaseBackup — portable logical backup & restore (Stage 18 DR / Phase 3).

Exports every table behind the ORM into a single JSON-serializable snapshot and
restores it into a fresh database, in foreign-key dependency order. It works over
the SQLAlchemy ``Base.metadata`` so it is backend-agnostic — the same code backs
up PostgreSQL in production and round-trips on SQLite in the test suite — which is
why it can be verified offline.

This is the *logical* tier of disaster recovery (portable, human-readable,
cross-version). The physical tier — ``pg_dump`` / ``neo4j-admin`` — lives in the
``scripts/`` shell wrappers for byte-exact, fast production backups. The two are
complementary: physical for routine PITR-style backups, logical for portability
and verification.

Restore is destructive: it recreates the schema and clears existing rows before
loading the snapshot, so it always lands on a clean, well-defined state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Uuid
from sqlalchemy.ext.asyncio import AsyncEngine

from app.infrastructure.database.base import Base

SNAPSHOT_VERSION = 1


def _encode(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    # Coerce numpy scalars/arrays (e.g. pgvector embeddings) to plain Python so
    # the snapshot stays JSON-serializable across backends.
    if hasattr(value, "tolist"):
        return value.tolist()
    if value.__class__.__module__ == "numpy":
        return value.item()
    return value


def _decode(column_type: Any, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(column_type, Uuid) and isinstance(value, str):
        return UUID(value)
    if isinstance(column_type, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


class DatabaseBackup:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def export(self, *, exclude_tables: set[str] | None = None) -> dict[str, Any]:
        """Read every table into a JSON-serializable snapshot.

        ``exclude_tables`` skips tables that are large and regenerable (e.g.
        ``memory_embeddings`` — vectors can be recomputed from memory content),
        keeping a backup fast and portable.
        """
        skip = exclude_tables or set()
        tables: dict[str, list[dict[str, Any]]] = {}
        async with self._engine.connect() as conn:
            for table in Base.metadata.sorted_tables:
                if table.name in skip:
                    continue
                result = await conn.execute(table.select())
                tables[table.name] = [
                    {k: _encode(v) for k, v in row.items()}
                    for row in result.mappings().all()
                ]
        return {
            "version": SNAPSHOT_VERSION,
            "tables": tables,
            "row_counts": {name: len(rows) for name, rows in tables.items()},
        }

    async def restore(self, snapshot: dict[str, Any]) -> dict[str, int]:
        """Recreate the schema and load ``snapshot``. Returns rows restored per table."""
        if snapshot.get("version") != SNAPSHOT_VERSION:
            raise ValueError(f"unsupported snapshot version: {snapshot.get('version')!r}")
        tables = snapshot["tables"]
        restored: dict[str, int] = {}
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Clear existing rows children-first (reverse dependency order).
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(table.delete())
            # Load parents-first so foreign keys resolve.
            for table in Base.metadata.sorted_tables:
                rows = tables.get(table.name, [])
                if not rows:
                    restored[table.name] = 0
                    continue
                col_types = {c.name: c.type for c in table.columns}
                decoded = [
                    {k: _decode(col_types.get(k), v) for k, v in row.items()}
                    for row in rows
                ]
                await conn.execute(table.insert(), decoded)
                restored[table.name] = len(decoded)
        return restored
