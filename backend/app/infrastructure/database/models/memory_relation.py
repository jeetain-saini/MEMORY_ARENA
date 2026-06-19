"""MemoryRelationModel — a typed, weighted edge between two memories."""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, JSONType, TimestampMixin


class MemoryRelationModel(TimestampMixin, Base):
    __tablename__ = "memory_relations"
    __table_args__ = (
        # Prevent duplicate edges of the same type between the same two memories.
        UniqueConstraint(
            "source_memory_id", "target_memory_id", "relation_type",
            name="uq_memory_relations_edge",
        ),
        Index("ix_memory_relations_source", "source_memory_id"),
        Index("ix_memory_relations_target", "target_memory_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_memory_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False
    )
    target_memory_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    meta: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
