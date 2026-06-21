"""add authentication columns to users

Revision ID: 0005_user_auth_columns
Revises: 0004_memory_summaries
Create Date: 2026-06-21

Stage 14 Phase 2 (authentication). Adds the credential and activation columns to
``users``. ``password_hash`` is nullable so accounts created before auth existed
remain valid (they simply cannot authenticate). ``is_active`` defaults to true
for existing rows; the ORM supplies it going forward.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_user_auth_columns"
down_revision: str | None = "0004_memory_summaries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    # Drop the server default now that existing rows are backfilled; the ORM
    # supplies the value going forward.
    op.alter_column("users", "is_active", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "is_active")
    op.drop_column("users", "password_hash")
