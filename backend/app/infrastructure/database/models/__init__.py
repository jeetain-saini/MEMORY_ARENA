"""ORM models — SQLAlchemy table mappings (a persistence detail).

Deliberately separate from domain/entities; mappers translate between them so
the DB schema can change without reshaping the domain.

Importing this package registers every model on ``Base.metadata`` — which is
what Alembic autogeneration and ``create_all`` rely on. Keep all models
re-exported here so a single import wires up the full schema.
"""

from app.infrastructure.database.models.memory import MemoryModel
from app.infrastructure.database.models.memory_embedding import (
    EMBEDDING_DIM,
    MemoryEmbeddingModel,
)
from app.infrastructure.database.models.memory_relation import MemoryRelationModel
from app.infrastructure.database.models.memory_score import MemoryScoreModel
from app.infrastructure.database.models.memory_summary import MemorySummaryModel
from app.infrastructure.database.models.memory_version import MemoryVersionModel
from app.infrastructure.database.models.user import UserModel

__all__ = [
    "UserModel",
    "MemoryModel",
    "MemoryScoreModel",
    "MemoryRelationModel",
    "MemoryVersionModel",
    "MemoryEmbeddingModel",
    "MemorySummaryModel",
    "EMBEDDING_DIM",
]
