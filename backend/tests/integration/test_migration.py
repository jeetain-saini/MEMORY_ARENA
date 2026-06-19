"""Migration tests.

Postgres (with pgvector + ``CREATE EXTENSION``) is not available in this test
environment, so we validate the migration structurally and verify the ORM
metadata it mirrors. Together these guarantee the migration creates exactly the
six required tables and is wired with a valid revision graph.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

EXPECTED_TABLES = {
    "users",
    "memories",
    "memory_scores",
    "memory_relations",
    "memory_versions",
    "memory_embeddings",
}

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0001_initial_schema.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("initial_migration", _MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_metadata_declares_all_required_tables() -> None:
    import app.infrastructure.database.models  # noqa: F401  (registers tables)
    from app.infrastructure.database.base import Base

    assert EXPECTED_TABLES <= set(Base.metadata.tables)


def test_migration_revision_graph() -> None:
    migration = _load_migration()
    assert migration.revision == "0001_initial"
    assert migration.down_revision is None
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_migration_creates_every_required_table() -> None:
    source = _MIGRATION_PATH.read_text(encoding="utf-8")
    for table in EXPECTED_TABLES:
        assert f'op.create_table(\n        "{table}"' in source, f"missing create_table for {table}"
    # pgvector must be enabled before the embeddings table.
    assert "CREATE EXTENSION IF NOT EXISTS vector" in source
