"""Structural tests for the 0009 audit_log migration (Stage 19.3)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0009_add_audit_log.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("audit_log_migration", _PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_graph() -> None:
    migration = _load()
    assert migration.revision == "0009_audit_log"
    assert migration.down_revision == "0008_user_role"
    assert callable(migration.upgrade) and callable(migration.downgrade)


def test_creates_indexed_append_only_table() -> None:
    source = _PATH.read_text(encoding="utf-8")
    assert 'create_table(\n        "audit_log"' in source
    assert 'ix_audit_log_user_id' in source       # tenant-trail index
    assert 'ix_audit_log_occurred_at' in source    # chronological index
    assert "deleted_at" not in source              # append-only (no soft delete)


def test_model_registered_on_metadata() -> None:
    from app.infrastructure.database.base import Base
    import app.infrastructure.database.models  # noqa: F401 - register models

    assert "audit_log" in Base.metadata.tables
