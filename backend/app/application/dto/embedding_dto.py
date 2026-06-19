"""EmbeddingRecord — the application/persistence representation of an embedding.

Carries the vector plus the metadata needed to version and migrate embeddings
over time (which model produced it, at what dimensionality, when). Plain
dataclass — no pydantic, no ORM — so it crosses the repository port cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class EmbeddingRecord:
    memory_id: UUID
    vector: list[float]
    model_name: str
    dimensions: int
    embedding_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_utcnow)
