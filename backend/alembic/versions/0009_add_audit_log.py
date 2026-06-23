"""add audit_log table

Revision ID: 0009_audit_log
Revises: 0008_user_role
Create Date: 2026-06-23

Stage 19.3 (audit logging). Creates the append-only ``audit_log`` table that the
durable PostgresAuditLog adapter writes to. Indexed on ``user_id`` (tenant trail
+ admin query) and ``occurred_at`` (chronological scans). ``details`` is JSON
(JSONB on PostgreSQL). Rows are immutable — no soft-delete column.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0009_audit_log"
down_revision: str | None = "0008_user_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("resource_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=True),
        sa.Column("details", _JSON, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_occurred_at", table_name="audit_log")
    op.drop_index("ix_audit_log_user_id", table_name="audit_log")
    op.drop_table("audit_log")
