"""Mapping between memories and graph nodes, plus entity extraction.

A memory becomes one graph node whose ``node_type`` is derived from its
``MemoryType``. Node properties carry the data graph-aware retrieval needs
(content, type, status, score) so expansion does not require extra DB calls.
"""

from __future__ import annotations

from app.application.dto.graph_dto import GraphNode, NodeType
from app.application.services.context.conflict_detector import STOPWORDS
from app.application.services.retrieval.bm25 import tokenize
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType

_TYPE_MAP: dict[MemoryType, NodeType] = {
    MemoryType.FACT: NodeType.FACT,
    MemoryType.GOAL: NodeType.GOAL,
    MemoryType.SKILL: NodeType.SKILL,
    MemoryType.PROJECT: NodeType.PROJECT,
    MemoryType.PREFERENCE: NodeType.PREFERENCE,
    MemoryType.EXPERIENCE: NodeType.MEMORY,
}


def node_type_for(memory_type: MemoryType) -> NodeType:
    return _TYPE_MAP.get(memory_type, NodeType.MEMORY)


def memory_to_node(memory: Memory) -> GraphNode:
    return GraphNode(
        node_id=str(memory.id),
        node_type=node_type_for(memory.memory_type),
        label=memory.content[:80],
        properties={
            "content": memory.content,
            "memory_type": memory.memory_type.value,
            "status": memory.status.value,
            "user_id": str(memory.user_id),
            "score": memory.total_score,
            "is_promoted": memory.is_promoted,
        },
    )


def extract_entities(text: str, *, min_length: int = 3) -> set[str]:
    """Significant terms used to relate memories (stopwords removed)."""
    return {
        token
        for token in tokenize(text)
        if len(token) >= min_length and token not in STOPWORDS
    }
