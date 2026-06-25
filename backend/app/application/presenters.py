"""Presenters — map domain entities to application response DTOs.

Keeps the domain→DTO translation in one place so every use case and service
returns an identical, stable shape to the delivery layer.
"""

from __future__ import annotations

from app.application.dto.memory_dto import CreateMemoryResponse
from app.domain.entities.memory import Memory


def memory_to_response(memory: Memory) -> CreateMemoryResponse:
    return CreateMemoryResponse(
        id=memory.id,
        user_id=memory.user_id,
        content=memory.content,
        memory_type=memory.memory_type,
        status=memory.status,
        total_score=memory.total_score,
        version=memory.version,
        is_promoted=memory.is_promoted,
        priority=memory.priority,
        category=memory.category,
        retrieval_count=memory.retrieval_count,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        metadata=dict(memory.metadata or {}),
    )
