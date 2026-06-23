"""add role to users

Revision ID: 0008_user_role
Revises: 0007_memory_lifecycle
Create Date: 2026-06-23

Stage 19.1 (RBAC). Adds a ``role`` column to ``users`` in three steps so existing
rows get a well-defined role before the constraint is enforced:

  1. add the column nullable,
  2. backfill ``role = 'user'`` (every pre-RBAC account is a least-privilege user),
  3. enforce NOT NULL with a ``'user'`` server default.

The domain ``User`` and the ORM column default both mirror ``'user'`` going
forward, so the invariant "every user has a non-null role" holds everywhere.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_user_role"
down_revision: str | None = "0007_memory_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. add nullable
    op.add_column("users", sa.Column("role", sa.String(length=32), nullable=True))
    # 2. backfill: every existing account is a least-privilege user
    op.execute("UPDATE users SET role = 'user' WHERE role IS NULL")
    # 3. enforce NOT NULL with a server default now that every row has a value
    op.alter_column(
        "users", "role",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default="user",
    )


def downgrade() -> None:
    op.drop_column("users", "role")
