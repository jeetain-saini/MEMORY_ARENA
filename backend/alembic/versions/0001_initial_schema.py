"""initial schema: users, memories, scores, relations, versions, embeddings

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-19

Creates the full Stage 3 persistence schema and enables the pgvector extension.
No data is generated — embeddings remain empty until Stage 4.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    # pgvector must exist before the embeddings table references the vector type.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "memories",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("memory_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_promoted", sa.Boolean(), nullable=False),
        sa.Column("meta", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_memories_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memories"),
    )
    op.create_index("ix_memories_user_id", "memories", ["user_id"])
    op.create_index("ix_memories_user_id_status", "memories", ["user_id", "status"])
    op.create_index("ix_memories_memory_type", "memories", ["memory_type"])

    op.create_table(
        "memory_scores",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("memory_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("utility", sa.Float(), nullable=False),
        sa.Column("frequency", sa.Float(), nullable=False),
        sa.Column("recency", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["memory_id"], ["memories.id"],
            name="fk_memory_scores_memory_id_memories", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memory_scores"),
        sa.UniqueConstraint("memory_id", name="uq_memory_scores_memory_id"),
    )
    op.create_index("ix_memory_scores_memory_id", "memory_scores", ["memory_id"])

    op.create_table(
        "memory_relations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_memory_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("target_memory_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("relation_type", sa.String(length=32), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("meta", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_memory_id"], ["memories.id"],
            name="fk_memory_relations_source_memory_id_memories", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_memory_id"], ["memories.id"],
            name="fk_memory_relations_target_memory_id_memories", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memory_relations"),
        sa.UniqueConstraint(
            "source_memory_id", "target_memory_id", "relation_type",
            name="uq_memory_relations_edge",
        ),
    )
    op.create_index("ix_memory_relations_source", "memory_relations", ["source_memory_id"])
    op.create_index("ix_memory_relations_target", "memory_relations", ["target_memory_id"])

    op.create_table(
        "memory_versions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("memory_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("memory_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("meta", JSONB(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["memory_id"], ["memories.id"],
            name="fk_memory_versions_memory_id_memories", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memory_versions"),
        sa.UniqueConstraint(
            "memory_id", "version_number", name="uq_memory_versions_memory_version"
        ),
    )
    op.create_index("ix_memory_versions_memory_id", "memory_versions", ["memory_id"])

    op.create_table(
        "memory_embeddings",
        sa.Column("embedding_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("memory_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("vector", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["memory_id"], ["memories.id"],
            name="fk_memory_embeddings_memory_id_memories", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("embedding_id", name="pk_memory_embeddings"),
        sa.UniqueConstraint(
            "memory_id", "model_name", name="uq_memory_embeddings_memory_model"
        ),
    )
    op.create_index("ix_memory_embeddings_memory_id", "memory_embeddings", ["memory_id"])


def downgrade() -> None:
    op.drop_table("memory_embeddings")
    op.drop_table("memory_versions")
    op.drop_table("memory_relations")
    op.drop_table("memory_scores")
    op.drop_table("memories")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS vector")
