"""Stage 17 integration tests: promotion, forgetting, clustering, retrieval
frequency, and extended analytics (SQLite + in-memory graph + dispatcher)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import TypeVar
from uuid import uuid4

from app.application.dto.graph_dto import GraphEdgeType
from app.application.services.intelligence.clustering_engine import ClusteringEngine
from app.application.services.intelligence.forgetting_engine import (
    ForgettingConfig,
    ForgettingEngine,
)
from app.application.services.intelligence.promotion_engine import (
    PromotionConfig,
    PromotionEngine,
)
from app.application.services.observability.memory_health_service import MemoryHealthService
from app.domain.entities.memory import Memory
from app.domain.entities.memory_score import MemoryScore
from app.domain.value_objects.memory_category import MemoryCategory
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


def _factory(engine) -> Callable[[], SQLAlchemyUnitOfWork]:
    sf = create_session_factory(engine)
    return lambda: SQLAlchemyUnitOfWork(sf)


async def _save(uow_factory, memory: Memory) -> None:
    async with uow_factory() as uow:
        await uow.memories.save(memory)
        await uow.commit()


# --- promotion (episodic -> semantic) --------------------------------------

def test_promotion_creates_semantic_with_promoted_from_edges() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()
        for _ in range(3):  # recurring episodic memory
            await _save(uowf, Memory.create(
                user_id=user, content="I am learning LangGraph",
                memory_type=MemoryType.EXPERIENCE))

        engine_svc = PromotionEngine(uowf, graph, InProcessEventDispatcher(),
                                     PromotionConfig(min_occurrences=2))
        created = await engine_svc.promote_user(user)
        assert len(created) == 1

        async with uowf() as uow:
            semantic = await uow.memories.get_by_id(created[0])
        assert semantic.category is MemoryCategory.SEMANTIC
        assert "LangGraph".lower() in semantic.content.lower()
        edges = await graph.get_edges(str(created[0]))
        promoted = [e for e in edges if e.edge_type is GraphEdgeType.PROMOTED_FROM]
        assert len(promoted) == 3  # one PROMOTED_FROM per preserved source

        # sources preserved (still present, still ACTIVE)
        async with uowf() as uow:
            all_mem = await uow.memories.list_for_analytics(user)
        episodic = [m for m in all_mem if m.category is MemoryCategory.EPISODIC]
        assert len(episodic) == 3 and all(m.status is MemoryStatus.ACTIVE for m in episodic)
        # idempotent: a second run promotes nothing new
        assert await engine_svc.promote_user(user) == []
        await engine.dispose()

    _run(scenario)


# --- forgetting ------------------------------------------------------------

def test_forgetting_sweep_marks_eligible_forgotten() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()
        old = datetime.now(timezone.utc) - timedelta(days=200)
        stale = Memory(user_id=user, content="ancient trivial note",
                       memory_type=MemoryType.FACT,
                       score=MemoryScore(importance=0.05, utility=0.1, frequency=0.0,
                                         recency=0.0, confidence=0.3),
                       created_at=old, updated_at=old)
        fresh = Memory.create(user_id=user, content="current important fact",
                              memory_type=MemoryType.FACT,
                              score=MemoryScore(importance=0.9, utility=0.5, frequency=0.5,
                                                recency=0.9, confidence=0.9))
        await _save(uowf, stale)
        await _save(uowf, fresh)

        fe = ForgettingEngine(uowf, graph, InProcessEventDispatcher(),
                              ForgettingConfig(min_age_days=90, max_importance=0.25))
        forgotten = await fe.sweep_user(user)
        assert forgotten == [stale.id]
        async with uowf() as uow:
            assert (await uow.memories.get_by_id(stale.id)).status is MemoryStatus.FORGOTTEN
            assert (await uow.memories.get_by_id(fresh.id)).status is MemoryStatus.ACTIVE
        await engine.dispose()

    _run(scenario)


# --- clustering ------------------------------------------------------------

def test_clustering_groups_related_and_writes_cluster_member_edges() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()
        for content in (
            "LangGraph orchestrates LangChain agents",
            "LangChain and LangGraph for RAG",
            "PostgreSQL Neo4j Redis datastores",
            "Redis cache alongside PostgreSQL",
        ):
            await _save(uowf, Memory.create(user_id=user, content=content,
                                            memory_type=MemoryType.FACT))

        ce = ClusteringEngine(uowf, graph)
        clusters = await ce.cluster_user(user)
        assert len(clusters) >= 1
        biggest = max(clusters, key=lambda c: c.size)
        assert biggest.size >= 2 and biggest.name
        # CLUSTER_MEMBER edges exist + members carry the cluster id in metadata
        rep_edges = await graph.get_edges(str(biggest.member_ids[0]))
        assert any(e.edge_type is GraphEdgeType.CLUSTER_MEMBER for e in rep_edges)
        async with uowf() as uow:
            member = await uow.memories.get_by_id(biggest.member_ids[1])
        assert member.metadata.get("cluster_id") == biggest.cluster_id
        await engine.dispose()

    _run(scenario)


# --- retrieval frequency ---------------------------------------------------

def test_record_retrievals_bulk_increments() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        a = Memory.create(user_id=user, content="alpha fact", memory_type=MemoryType.FACT)
        b = Memory.create(user_id=user, content="beta fact", memory_type=MemoryType.FACT)
        await _save(uowf, a)
        await _save(uowf, b)
        async with uowf() as uow:
            await uow.memories.record_retrievals([a.id, b.id])
            await uow.commit()
        async with uowf() as uow:
            ra = await uow.memories.get_by_id(a.id)
        assert ra.retrieval_count == 1 and ra.last_retrieved_at is not None
        await engine.dispose()

    _run(scenario)


# --- extended analytics ----------------------------------------------------

def test_health_metrics_include_stage17_fields() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()
        await _save(uowf, Memory.create(user_id=user, content="learning Rust daily",
                                        memory_type=MemoryType.EXPERIENCE))
        await _save(uowf, Memory.create(user_id=user, content="timezone is IST",
                                        memory_type=MemoryType.FACT))

        svc = MemoryHealthService(SQLAlchemyUnitOfWork(create_session_factory(engine)), graph)
        health = await svc.get_health(user_id=user)
        assert health.episodic_count == 1
        assert health.semantic_count == 1
        assert health.average_memory_age_days >= 0.0
        assert set(health.importance_distribution.keys())  # buckets present
        assert "average" in health.retrieval_frequency_stats
        await engine.dispose()

    _run(scenario)
