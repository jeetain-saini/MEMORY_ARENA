"""Structural tests for the 0006 user tenant_id migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0006_add_user_tenant_id.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("user_tenant_migration", _PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_graph() -> None:
    migration = _load()
    assert migration.revision == "0006_user_tenant_id"
    assert migration.down_revision == "0005_user_auth_columns"
    assert callable(migration.upgrade) and callable(migration.downgrade)


def test_three_step_add_backfill_enforce() -> None:
    source = _PATH.read_text(encoding="utf-8")
    assert 'sa.Column("tenant_id"' in source
    assert "UPDATE users SET tenant_id = id" in source  # backfill
    assert 'nullable=False' in source  # enforce NOT NULL after backfill


def test_model_tenant_id_is_not_null() -> None:
    from app.infrastructure.database.models.user import UserModel

    column = UserModel.__table__.columns["tenant_id"]
    assert column.nullable is False
