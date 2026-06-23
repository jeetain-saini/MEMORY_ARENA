"""Structural tests for the 0008 user role migration (Stage 19.1)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0008_add_user_role.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("user_role_migration", _PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_graph() -> None:
    migration = _load()
    assert migration.revision == "0008_user_role"
    assert migration.down_revision == "0007_memory_lifecycle"
    assert callable(migration.upgrade) and callable(migration.downgrade)


def test_three_step_add_backfill_enforce() -> None:
    source = _PATH.read_text(encoding="utf-8")
    assert 'sa.Column("role"' in source
    assert "UPDATE users SET role = 'user'" in source  # backfill
    assert 'nullable=False' in source  # enforce NOT NULL after backfill
    assert 'server_default="user"' in source  # default for future inserts


def test_model_role_is_not_null_with_default() -> None:
    from app.infrastructure.database.models.user import UserModel

    column = UserModel.__table__.columns["role"]
    assert column.nullable is False
    assert column.server_default is not None
