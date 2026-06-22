"""Mappers — translate between domain entities and ORM models.

Mappers are the boundary that keeps the domain pure: domain objects never know
about SQLAlchemy, and models never carry business behavior. Only this module
imports both sides. Each pair is a plain function so it is trivially unit-tested
without a database.
"""

from __future__ import annotations

from uuid import UUID

from app.application.dto.embedding_dto import EmbeddingRecord
from app.domain.entities.memory import Memory
from app.domain.entities.memory_relation import MemoryRelation
from app.domain.entities.memory_score import MemoryScore
from app.domain.entities.memory_summary import MemorySummary
from app.domain.entities.memory_version import MemoryVersion
from app.domain.entities.user import User
from app.domain.value_objects.memory_category import MemoryCategory, default_category
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType
from app.domain.value_objects.relation_type import RelationType
from app.infrastructure.database.models.memory import MemoryModel
from app.infrastructure.database.models.memory_embedding import MemoryEmbeddingModel
from app.infrastructure.database.models.memory_relation import MemoryRelationModel
from app.infrastructure.database.models.memory_score import MemoryScoreModel
from app.infrastructure.database.models.memory_summary import MemorySummaryModel
from app.infrastructure.database.models.memory_version import MemoryVersionModel
from app.infrastructure.database.models.user import UserModel


# --- User <-> UserModel ----------------------------------------------------
def user_to_model(user: User) -> UserModel:
    return UserModel(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        password_hash=user.password_hash,
        is_active=user.is_active,
        tenant_id=user.tenant_id,
    )


def model_to_user(model: UserModel) -> User:
    return User(
        id=model.id,
        email=model.email,
        display_name=model.display_name,
        password_hash=model.password_hash,
        is_active=model.is_active,
        tenant_id=model.tenant_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


# --- MemoryScore <-> MemoryScoreModel --------------------------------------
def score_to_model(memory_id, score: MemoryScore) -> MemoryScoreModel:
    return MemoryScoreModel(
        memory_id=memory_id,
        importance=score.importance,
        utility=score.utility,
        frequency=score.frequency,
        recency=score.recency,
        confidence=score.confidence,
    )


def model_to_score(model: MemoryScoreModel | None) -> MemoryScore:
    if model is None:
        return MemoryScore.neutral()
    return MemoryScore(
        importance=model.importance,
        utility=model.utility,
        frequency=model.frequency,
        recency=model.recency,
        confidence=model.confidence,
    )


def apply_score_to_model(model: MemoryScoreModel, score: MemoryScore) -> None:
    """Update an existing score row in place (used on update)."""
    model.importance = score.importance
    model.utility = score.utility
    model.frequency = score.frequency
    model.recency = score.recency
    model.confidence = score.confidence


# --- Memory <-> MemoryModel ------------------------------------------------
def memory_to_model(memory: Memory) -> MemoryModel:
    return MemoryModel(
        id=memory.id,
        user_id=memory.user_id,
        content=memory.content,
        memory_type=memory.memory_type.value,
        status=memory.status.value,
        version=memory.version,
        is_promoted=memory.is_promoted,
        priority=memory.priority,
        category=(memory.category or default_category(memory.memory_type)).value,
        retrieval_count=memory.retrieval_count,
        last_retrieved_at=memory.last_retrieved_at,
        meta=dict(memory.metadata),
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        score=score_to_model(memory.id, memory.score),
    )


def apply_memory_to_model(model: MemoryModel, memory: Memory) -> None:
    """Update mutable fields of an existing memory row in place."""
    model.content = memory.content
    model.memory_type = memory.memory_type.value
    model.status = memory.status.value
    model.version = memory.version
    model.is_promoted = memory.is_promoted
    model.priority = memory.priority
    model.category = (memory.category or default_category(memory.memory_type)).value
    model.retrieval_count = memory.retrieval_count
    model.last_retrieved_at = memory.last_retrieved_at
    model.meta = dict(memory.metadata)
    model.updated_at = memory.updated_at


def model_to_memory(model: MemoryModel) -> Memory:
    return Memory(
        id=model.id,
        user_id=model.user_id,
        content=model.content,
        memory_type=MemoryType(model.memory_type),
        status=MemoryStatus(model.status),
        score=model_to_score(model.score),
        metadata=dict(model.meta or {}),
        version=model.version,
        is_promoted=model.is_promoted,
        priority=model.priority,
        category=MemoryCategory(model.category) if model.category else None,
        retrieval_count=model.retrieval_count or 0,
        last_retrieved_at=model.last_retrieved_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


# --- MemoryRelation <-> MemoryRelationModel --------------------------------
def relation_to_model(relation: MemoryRelation) -> MemoryRelationModel:
    return MemoryRelationModel(
        id=relation.id,
        source_memory_id=relation.source_memory_id,
        target_memory_id=relation.target_memory_id,
        relation_type=relation.relation_type.value,
        weight=relation.weight,
        meta=dict(relation.metadata),
        created_at=relation.created_at,
    )


def model_to_relation(model: MemoryRelationModel) -> MemoryRelation:
    return MemoryRelation(
        id=model.id,
        source_memory_id=model.source_memory_id,
        target_memory_id=model.target_memory_id,
        relation_type=RelationType(model.relation_type),
        weight=model.weight,
        metadata=dict(model.meta or {}),
        created_at=model.created_at,
    )


# --- MemoryVersion <-> MemoryVersionModel ----------------------------------
def version_to_model(version: MemoryVersion) -> MemoryVersionModel:
    return MemoryVersionModel(
        id=version.id,
        memory_id=version.memory_id,
        version_number=version.version_number,
        content=version.content,
        memory_type=version.memory_type.value,
        status=version.status.value,
        meta=dict(version.metadata),
        reason=version.reason,
        created_at=version.created_at,
    )


def model_to_version(model: MemoryVersionModel) -> MemoryVersion:
    return MemoryVersion(
        id=model.id,
        memory_id=model.memory_id,
        version_number=model.version_number,
        content=model.content,
        memory_type=MemoryType(model.memory_type),
        status=MemoryStatus(model.status),
        metadata=dict(model.meta or {}),
        reason=model.reason,
        created_at=model.created_at,
    )


# --- EmbeddingRecord <-> MemoryEmbeddingModel ------------------------------
def embedding_to_model(record: EmbeddingRecord) -> MemoryEmbeddingModel:
    return MemoryEmbeddingModel(
        embedding_id=record.embedding_id,
        memory_id=record.memory_id,
        vector=list(record.vector),
        model_name=record.model_name,
        dimensions=record.dimensions,
        created_at=record.created_at,
    )


def model_to_embedding(model: MemoryEmbeddingModel) -> EmbeddingRecord:
    return EmbeddingRecord(
        embedding_id=model.embedding_id,
        memory_id=model.memory_id,
        vector=list(model.vector),
        model_name=model.model_name,
        dimensions=model.dimensions,
        created_at=model.created_at,
    )


# --- MemorySummary <-> MemorySummaryModel ----------------------------------
def summary_to_model(summary: MemorySummary) -> MemorySummaryModel:
    return MemorySummaryModel(
        id=summary.id,
        user_id=summary.user_id,
        scope=summary.scope.value,
        summary_text=summary.summary_text,
        source_memory_ids=[str(mid) for mid in summary.source_memory_ids],
        source_count=summary.source_count,
        version=summary.version,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
    )


def model_to_summary(model: MemorySummaryModel) -> MemorySummary:
    return MemorySummary(
        id=model.id,
        user_id=model.user_id,
        scope=MemoryType(model.scope),
        summary_text=model.summary_text,
        source_memory_ids=[UUID(mid) for mid in (model.source_memory_ids or [])],
        source_count=model.source_count,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
