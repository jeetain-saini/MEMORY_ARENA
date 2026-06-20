"""add memory_summaries table

Revision ID: 0004_memory_summaries
Revises: 0003_embedding_dims
Create Date: 2026-06-20

Stage 11 Phase C: rolling, derived per-scope summaries stored separately from
memories. One row per (user_id, scope); the summarization workflow upserts it.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_memory_summaries"
down_revision: str | None = "0003_embedding_dims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_summaries",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_memory_ids", sa.JSON(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_memory_summaries_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memory_summaries"),
        sa.UniqueConstraint("user_id", "scope", name="uq_memory_summaries_user_id_scope"),
    )
    op.create_index("ix_memory_summaries_user_id", "memory_summaries", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_memory_summaries_user_id", table_name="memory_summaries")
    op.drop_table("memory_summaries")
