"""Structural tests for the 0005 user auth-columns migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0005_add_user_auth_columns.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("user_auth_migration", _PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_graph() -> None:
    migration = _load()
    assert migration.revision == "0005_user_auth_columns"
    assert migration.down_revision == "0004_memory_summaries"
    assert callable(migration.upgrade) and callable(migration.downgrade)


def test_adds_auth_columns() -> None:
    source = _PATH.read_text(encoding="utf-8")
    assert '"password_hash"' in source
    assert '"is_active"' in source


def test_model_has_auth_columns() -> None:
    from app.infrastructure.database.models.user import UserModel

    columns = UserModel.__table__.columns
    assert "password_hash" in columns
    assert columns["password_hash"].nullable is True
    assert "is_active" in columns
