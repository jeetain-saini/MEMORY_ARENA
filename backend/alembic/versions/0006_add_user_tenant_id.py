"""add tenant_id to users

Revision ID: 0006_user_tenant_id
Revises: 0005_user_auth_columns
Create Date: 2026-06-21

Stage 14 Phase 3 (tenant isolation). Adds ``tenant_id`` to ``users`` in three
steps so existing rows get a well-defined tenant before the constraint is
enforced:

  1. add the column nullable,
  2. backfill ``tenant_id = id`` (each user is initially their own tenant),
  3. enforce NOT NULL.

The domain ``User`` and the ORM column default both mirror ``id`` going forward,
so the invariant "every user has a non-null tenant_id" holds everywhere.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_user_tenant_id"
down_revision: str | None = "0005_user_auth_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. add nullable
    op.add_column("users", sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=True))
    # 2. backfill: each existing user becomes their own tenant
    op.execute("UPDATE users SET tenant_id = id WHERE tenant_id IS NULL")
    # 3. enforce NOT NULL now that every row has a value
    op.alter_column("users", "tenant_id", existing_type=sa.Uuid(as_uuid=True), nullable=False)
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_column("users", "tenant_id")
