"""Unit tests for MemoryHealthService (Stage 13).

Deterministic: a fake UoW supplies fixed memories/summaries, the real in-memory
graph supplies density, and a fixed ``now`` makes growth windows reproducible.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.application.dto.graph_dto import GraphEdge, GraphEdgeType, GraphNode, NodeType
from app.application.services.observability.memory_health_service import MemoryHealthService
from app.domain.entities.memory import Memory
from app.domain.entities.memory_score import MemoryScore
from app.domain.entities.memory_summary import MemorySummary
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository

NOW = datetime(2026, 6, 20, tzinfo=timezone.utc)
USER = uuid4()


class _FakeMemRepo:
    def __init__(self, memories: list[Memory]) -> None:
        self._memories = memories

    async def list_for_analytics(self, user_id=None) -> list[Memory]:
        return list(self._memories)


class _FakeSumRepo:
    def __init__(self, summaries: list[MemorySummary]) -> None:
        self._summaries = summaries

    async def list_for_user(self, user_id) -> list[MemorySummary]:
        return list(self._summaries)


class _FakeUoW:
    def __init__(self, memories, summaries) -> None:
        self.memories = _FakeMemRepo(memories)
        self.summaries = _FakeSumRepo(summaries)

    async def __aenter__(self) -> "_FakeUoW":
        return self

    async def __aexit__(self, *exc) -> None:
        return None


def _memory(
    *,
    memory_type=MemoryType.FACT,
    status=MemoryStatus.ACTIVE,
    is_promoted=False,
    age_days=1,
    frequency=0.0,
) -> Memory:
    return Memory(
        user_id=USER,
        content=f"memory {memory_type.value}",
        memory_type=memory_type,
        status=status,
        is_promoted=is_promoted,
        score=MemoryScore(frequency=frequency),
        created_at=NOW - timedelta(days=age_days),
        updated_at=NOW - timedelta(days=age_days),
    )


def _graph() -> InMemoryGraphRepository:
    repo = InMemoryGraphRepository()

    async def seed() -> None:
        for nid in ("n1", "n2", "n3"):
            await repo.create_node(
                GraphNode(node_id=nid, node_type=NodeType.MEMORY, label=nid, properties={"user_id": str(USER)})
            )
        await repo.create_edge(GraphEdge("n1", "n2", GraphEdgeType.RELATED_TO))
        await repo.create_edge(GraphEdge("n2", "n3", GraphEdgeType.RELATED_TO))

    asyncio.run(seed())
    return repo


def _health(memories, summaries, graph=None):
    service = MemoryHealthService(_FakeUoW(memories, summaries), graph or InMemoryGraphRepository())
    return asyncio.run(service.get_health(USER, now=NOW))


def test_lifecycle_composition_and_rates() -> None:
    memories = [
        _memory(),                                    # active
        _memory(is_promoted=True),                    # active + promoted
        _memory(status=MemoryStatus.ARCHIVED),        # archived
        _memory(status=MemoryStatus.ARCHIVED),        # archived
    ]
    h = _health(memories, [])
    assert h.total_memories == 4
    assert h.active_memories == 2
    assert h.archived_memories == 2
    assert h.promoted_memories == 1
    assert h.promotion_rate == 0.25
    assert h.archive_rate == 0.5


def test_growth_windows() -> None:
    memories = [
        _memory(age_days=3),    # in 7 and 30
        _memory(age_days=20),   # in 30 only
        _memory(age_days=40),   # outside both
    ]
    h = _health(memories, [])
    assert h.created_last_7_days == 1
    assert h.created_last_30_days == 2


def test_avg_reinforcement_signal_is_mean_frequency_over_active() -> None:
    memories = [
        _memory(frequency=0.2),
        _memory(frequency=0.4),
        _memory(status=MemoryStatus.ARCHIVED, frequency=1.0),  # excluded (not active)
    ]
    h = _health(memories, [])
    assert h.avg_reinforcement_signal == 0.3


def test_graph_density() -> None:
    h = _health([_memory()], [], graph=_graph())
    assert h.graph_nodes == 3
    assert h.graph_edges == 2
    assert h.graph_density == round(2 / 3, 4)


def test_summary_coverage_partial() -> None:
    memories = [
        _memory(memory_type=MemoryType.PROJECT),
        _memory(memory_type=MemoryType.GOAL),
    ]
    summaries = [
        MemorySummary.create(
            user_id=USER, scope=MemoryType.PROJECT, summary_text="p", source_memory_ids=[]
        )
    ]
    h = _health(memories, summaries)
    assert h.summary_scopes_expected == 2   # PROJECT + GOAL have active memories
    assert h.summary_scopes_present == 1    # only PROJECT summarized
    assert h.summary_coverage == 0.5


def test_summary_coverage_full_when_nothing_expected() -> None:
    # No PROJECT/GOAL/EXPERIENCE memories -> nothing to summarize -> full coverage.
    h = _health([_memory(memory_type=MemoryType.FACT)], [])
    assert h.summary_scopes_expected == 0
    assert h.summary_coverage == 1.0


def test_notes_flag_deferred_and_proxy_metrics() -> None:
    h = _health([_memory()], [])
    assert "retrieval_frequency" in h.notes
    assert "reinforcement_frequency" in h.notes


def test_empty_corpus_is_safe() -> None:
    h = _health([], [])
    assert h.total_memories == 0
    assert h.promotion_rate == 0.0
    assert h.archive_rate == 0.0
    assert h.average_score == 0.0
    assert h.graph_density == 0.0
