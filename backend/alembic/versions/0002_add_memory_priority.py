"""add priority column to memories

Revision ID: 0002_memory_priority
Revises: 0001_initial
Create Date: 2026-06-19

Stage 5: memory promotion raises a numeric priority. Existing rows default to 0.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_memory_priority"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memories",
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
    )
    # Drop the server default now that existing rows are backfilled; the ORM
    # supplies the value going forward.
    op.alter_column("memories", "priority", server_default=None)


def downgrade() -> None:
    op.drop_column("memories", "priority")
