"""MemoryScoreModel — the five score components, one row per memory."""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin


class MemoryScoreModel(TimestampMixin, Base):
    __tablename__ = "memory_scores"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("memories.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # exactly one score per memory
        index=True,
    )
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    utility: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    frequency: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    recency: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    memory: Mapped["MemoryModel"] = relationship(back_populates="score")  # noqa: F821
