"""MemoryEmbeddingModel — pgvector-backed embedding storage (schema only).

Stage 3 establishes the table and the ``vector`` column; **no embeddings are
generated and no similarity search is performed yet**. Defining it now means the
schema, migrations, and foreign keys are settled before Stage 4 plugs in an
embedding model — adding vectors later becomes data work, not a schema rewrite.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, Vector

# Default embedding dimensionality (matches PGVECTOR_DIMENSIONS in .env.example).
EMBEDDING_DIM = 1536


class MemoryEmbeddingModel(TimestampMixin, Base):
    __tablename__ = "memory_embeddings"
    __table_args__ = (
        UniqueConstraint("memory_id", "model_name", name="uq_memory_embeddings_memory_model"),
        Index("ix_memory_embeddings_memory_id", "memory_id"),
    )

    embedding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    memory_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False
    )
    vector: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Explicit dimensionality aids model-migration queries (find rows to re-embed).
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False, default=EMBEDDING_DIM)
