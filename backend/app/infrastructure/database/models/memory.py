"""MemoryModel — persistence mapping of the Memory aggregate root.

Enums are stored as their string values (portable across dialects, no DB enum
types to migrate). ``metadata`` is a reserved attribute name on declarative
classes, so the JSON column is exposed as ``meta`` (DB column ``meta``); the
mapper bridges it to the domain's ``metadata``. Soft-deletable.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, JSONType, SoftDeleteMixin, TimestampMixin


class MemoryModel(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "memories"
    __table_args__ = (
        # Hot path: "active memories for a user" — composite index.
        Index("ix_memories_user_id_status", "user_id", "status"),
        Index("ix_memories_memory_type", "memory_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_promoted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    meta: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    # One-to-one score; loaded eagerly by repositories when needed.
    score: Mapped["MemoryScoreModel"] = relationship(  # noqa: F821
        back_populates="memory",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
