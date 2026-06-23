"""UserModel — the owner of memories (minimal in Stage 3)."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, SoftDeleteMixin, TimestampMixin


class UserModel(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Stage 14 Phase 2 (authentication). Nullable so users seeded before auth
    # existed remain valid (they simply cannot authenticate).
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    # Stage 14 Phase 3 (tenant isolation). NOT NULL; when an insert omits it the
    # column default mirrors the row's id, so each user is initially their own
    # tenant (matching the migration backfill and the domain invariant).
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        default=lambda ctx: ctx.get_current_parameters()["id"],
        index=True,
    )
    # RBAC role (Stage 19.1). NOT NULL with a "user" default/server_default, so
    # existing rows and inserts that omit it are least-privilege users (matching
    # the migration backfill and the domain default).
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default="user", server_default="user"
    )
