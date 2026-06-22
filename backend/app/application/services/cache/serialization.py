"""JSON (de)serialization for the cached read DTOs (application-layer, approved).

The cache stores opaque JSON strings; these helpers are the single place that
knows a DTO's shape, so the cache adapters stay generic. Round-trips are covered
by unit tests (incl. UUID/dict fields).
"""

from __future__ import annotations

import json
from uuid import UUID

from app.application.dto.analytics_dto import MemoryAnalytics
from app.application.dto.health_dto import MemoryHealth


def dump_analytics(value: MemoryAnalytics) -> str:
    return json.dumps(
        {
            "total_memories": value.total_memories,
            "active_memories": value.active_memories,
            "archived_memories": value.archived_memories,
            "promoted_memories": value.promoted_memories,
            "average_score": value.average_score,
            "score_distribution": value.score_distribution,
        }
    )


def load_analytics(raw: str) -> MemoryAnalytics:
    d = json.loads(raw)
    return MemoryAnalytics(
        total_memories=d["total_memories"],
        active_memories=d["active_memories"],
        archived_memories=d["archived_memories"],
        promoted_memories=d["promoted_memories"],
        average_score=d["average_score"],
        score_distribution=d["score_distribution"],
    )


def dump_health(value: MemoryHealth) -> str:
    payload = {
        "user_id": str(value.user_id) if value.user_id is not None else None,
        "total_memories": value.total_memories,
        "active_memories": value.active_memories,
        "archived_memories": value.archived_memories,
        "promoted_memories": value.promoted_memories,
        "promotion_rate": value.promotion_rate,
        "archive_rate": value.archive_rate,
        "created_last_7_days": value.created_last_7_days,
        "created_last_30_days": value.created_last_30_days,
        "average_score": value.average_score,
        "avg_reinforcement_signal": value.avg_reinforcement_signal,
        "graph_nodes": value.graph_nodes,
        "graph_edges": value.graph_edges,
        "graph_density": value.graph_density,
        "summary_scopes_expected": value.summary_scopes_expected,
        "summary_scopes_present": value.summary_scopes_present,
        "summary_coverage": value.summary_coverage,
        "contradiction_count": value.contradiction_count,
        "superseded_count": value.superseded_count,
        "type_distribution": value.type_distribution,
        "average_importance": value.average_importance,
        "average_confidence": value.average_confidence,
        "forgotten_count": value.forgotten_count,
        "episodic_count": value.episodic_count,
        "semantic_count": value.semantic_count,
        "cluster_count": value.cluster_count,
        "promoted_from_count": value.promoted_from_count,
        "average_memory_age_days": value.average_memory_age_days,
        "retrieval_frequency_stats": value.retrieval_frequency_stats,
        "importance_distribution": value.importance_distribution,
        "confidence_distribution": value.confidence_distribution,
        "notes": value.notes,
    }
    return json.dumps(payload)


def load_health(raw: str) -> MemoryHealth:
    d = json.loads(raw)
    uid = d["user_id"]
    return MemoryHealth(
        user_id=UUID(uid) if uid is not None else None,
        total_memories=d["total_memories"],
        active_memories=d["active_memories"],
        archived_memories=d["archived_memories"],
        promoted_memories=d["promoted_memories"],
        promotion_rate=d["promotion_rate"],
        archive_rate=d["archive_rate"],
        created_last_7_days=d["created_last_7_days"],
        created_last_30_days=d["created_last_30_days"],
        average_score=d["average_score"],
        avg_reinforcement_signal=d["avg_reinforcement_signal"],
        graph_nodes=d["graph_nodes"],
        graph_edges=d["graph_edges"],
        graph_density=d["graph_density"],
        summary_scopes_expected=d["summary_scopes_expected"],
        summary_scopes_present=d["summary_scopes_present"],
        summary_coverage=d["summary_coverage"],
        contradiction_count=d.get("contradiction_count", 0),
        superseded_count=d.get("superseded_count", 0),
        type_distribution=d.get("type_distribution", {}),
        average_importance=d.get("average_importance", 0.0),
        average_confidence=d.get("average_confidence", 0.0),
        forgotten_count=d.get("forgotten_count", 0),
        episodic_count=d.get("episodic_count", 0),
        semantic_count=d.get("semantic_count", 0),
        cluster_count=d.get("cluster_count", 0),
        promoted_from_count=d.get("promoted_from_count", 0),
        average_memory_age_days=d.get("average_memory_age_days", 0.0),
        retrieval_frequency_stats=d.get("retrieval_frequency_stats", {}),
        importance_distribution=d.get("importance_distribution", {}),
        confidence_distribution=d.get("confidence_distribution", {}),
        notes=d["notes"],
    )
