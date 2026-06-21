"""Round-trip tests for cached-DTO JSON serialization + cache keys."""

from __future__ import annotations

from uuid import uuid4

from app.application.dto.analytics_dto import MemoryAnalytics
from app.application.dto.health_dto import MemoryHealth
from app.application.services.cache.cache_keys import (
    analytics_key,
    health_key,
    invalidation_keys,
)
from app.application.services.cache.serialization import (
    dump_analytics,
    dump_health,
    load_analytics,
    load_health,
)


def test_analytics_roundtrip() -> None:
    a = MemoryAnalytics(
        total_memories=5, active_memories=4, archived_memories=1, promoted_memories=2,
        average_score=0.37, score_distribution={"0.0-0.2": 1, "0.2-0.4": 4},
    )
    assert load_analytics(dump_analytics(a)) == a


def test_health_roundtrip_with_uuid_and_dicts() -> None:
    uid = uuid4()
    h = MemoryHealth(
        user_id=uid, total_memories=3, active_memories=2, archived_memories=1,
        promoted_memories=0, promotion_rate=0.0, archive_rate=0.333,
        created_last_7_days=1, created_last_30_days=2, average_score=0.4,
        avg_reinforcement_signal=0.2, graph_nodes=3, graph_edges=2, graph_density=0.6667,
        summary_scopes_expected=1, summary_scopes_present=1, summary_coverage=1.0,
        notes={"retrieval_frequency": "not tracked"},
    )
    restored = load_health(dump_health(h))
    assert restored == h
    assert restored.user_id == uid


def test_health_roundtrip_global_none_user() -> None:
    h = MemoryHealth(
        user_id=None, total_memories=0, active_memories=0, archived_memories=0,
        promoted_memories=0, promotion_rate=0.0, archive_rate=0.0,
        created_last_7_days=0, created_last_30_days=0, average_score=0.0,
        avg_reinforcement_signal=0.0, graph_nodes=0, graph_edges=0, graph_density=0.0,
        summary_scopes_expected=0, summary_scopes_present=0, summary_coverage=1.0, notes={},
    )
    assert load_health(dump_health(h)) == h


def test_cache_keys() -> None:
    uid = uuid4()
    assert analytics_key(uid) == f"analytics:user:{uid}"
    assert analytics_key(None) == "analytics:global"
    assert health_key(uid) == f"health:user:{uid}"
    assert health_key(None) == "health:global"


def test_invalidation_keys_cover_user_and_global() -> None:
    uid = uuid4()
    keys = invalidation_keys(uid)
    assert keys == [
        f"analytics:user:{uid}", "analytics:global",
        f"health:user:{uid}", "health:global",
    ]
