"""add memory category + retrieval-frequency tracking (Stage 17)

Revision ID: 0007_memory_lifecycle
Revises: 0006_user_tenant_id
Create Date: 2026-06-22

Stage 17 (self-evolving memory). Adds, to ``memories``:

  * ``category``           — episodic | semantic (default semantic; backfilled
                             from memory_type so existing rows get a value)
  * ``retrieval_count``    — times the memory has been returned by retrieval
  * ``last_retrieved_at``  — last retrieval timestamp (nullable)

New lifecycle statuses (SUPERSEDED / FORGOTTEN) need no schema change — ``status``
is already a string column. Existing ARCHIVED rows are intentionally NOT
backfilled to SUPERSEDED. Fully reversible.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_memory_lifecycle"
down_revision: str | None = "0006_user_tenant_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memories",
        sa.Column("category", sa.String(length=16), nullable=False, server_default="semantic"),
    )
    op.add_column(
        "memories",
        sa.Column("retrieval_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "memories",
        sa.Column("last_retrieved_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill category from memory_type: EXPERIENCE -> episodic, else semantic.
    op.execute("UPDATE memories SET category = 'episodic' WHERE memory_type = 'experience'")
    op.execute("UPDATE memories SET category = 'semantic' WHERE memory_type <> 'experience'")


def downgrade() -> None:
    op.drop_column("memories", "last_retrieved_at")
    op.drop_column("memories", "retrieval_count")
    op.drop_column("memories", "category")
