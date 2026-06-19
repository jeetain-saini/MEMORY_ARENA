"""add dimensions column to memory_embeddings

Revision ID: 0003_embedding_dims
Revises: 0002_memory_priority
Create Date: 2026-06-19

Stage 6: track embedding dimensionality explicitly to support model migration.
Existing rows (none yet) default to the standard 1536.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_embedding_dims"
down_revision: str | None = "0002_memory_priority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memory_embeddings",
        sa.Column("dimensions", sa.Integer(), nullable=False, server_default="1536"),
    )
    op.alter_column("memory_embeddings", "dimensions", server_default=None)


def downgrade() -> None:
    op.drop_column("memory_embeddings", "dimensions")
