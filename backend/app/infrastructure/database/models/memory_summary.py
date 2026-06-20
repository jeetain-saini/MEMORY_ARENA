"""MemorySummaryModel — persistence mapping of a rolling memory summary.

A derived artifact stored separately from memories. One row per
``(user_id, scope)`` (enforced by a unique constraint), upserted by the
summarization workflow. ``source_memory_ids`` is a JSON list of the memory ids
the summary was built from (provenance).
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, JSONType, TimestampMixin


class MemorySummaryModel(TimestampMixin, Base):
    __tablename__ = "memory_summaries"
    __table_args__ = (
        UniqueConstraint("user_id", "scope", name="uq_memory_summaries_user_id_scope"),
        Index("ix_memory_summaries_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_memory_ids: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
