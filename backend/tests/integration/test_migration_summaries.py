"""Structural tests for the 0004 memory_summaries migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0004_add_memory_summaries.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("summary_migration", _PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_graph() -> None:
    migration = _load()
    assert migration.revision == "0004_memory_summaries"
    assert migration.down_revision == "0003_embedding_dims"
    assert callable(migration.upgrade) and callable(migration.downgrade)


def test_creates_memory_summaries_table() -> None:
    source = _PATH.read_text(encoding="utf-8")
    assert 'op.create_table(\n        "memory_summaries"' in source
    assert "uq_memory_summaries_user_id_scope" in source


def test_metadata_declares_summary_table() -> None:
    import app.infrastructure.database.models  # noqa: F401
    from app.infrastructure.database.base import Base

    assert "memory_summaries" in Base.metadata.tables
