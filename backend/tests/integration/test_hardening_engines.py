"""Production-hardening tests (Phases 2-4):

* Phase 2 — clustering skips PostgreSQL writes when cluster_id is unchanged.
* Phase 3 — promotion reinforces instead of duplicating semantic memories.
* Phase 4 — stale CLUSTER_MEMBER edges are pruned; valid/other edges retained.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

from app.application.dto.graph_dto import GraphEdge, GraphEdgeType
from app.application.services.intelligence.clustering_engine import ClusteringEngine
from app.application.services.intelligence.promotion_engine import (
    PromotionConfig,
    PromotionEngine,
)
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_category import MemoryCategory
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from app.infrastructure.observability.in_memory_metrics import InMemoryMetricsSink
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


def _factory(engine) -> Callable[[], SQLAlchemyUnitOfWork]:
    sf = create_session_factory(engine)
    return lambda: SQLAlchemyUnitOfWork(sf)


async def _save(uowf, memory: Memory) -> None:
    async with uowf() as uow:
        await uow.memories.save(memory)
        await uow.commit()


async def _count_edges(graph: InMemoryGraphRepository, edge_type: GraphEdgeType) -> int:
    return sum(1 for e in graph._edges.values() if e.edge_type is edge_type)


# --- Phase 2: clustering write amplification -------------------------------

def test_clustering_skips_unchanged_writes() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()
        metrics = InMemoryMetricsSink()
        for content in (
            "LangGraph orchestrates LangChain agents",
            "LangChain and LangGraph for RAG",
            "PostgreSQL Neo4j Redis datastores",
            "Redis cache alongside PostgreSQL",
        ):
            await _save(uowf, Memory.create(user_id=user, content=content,
                                            memory_type=MemoryType.FACT))

        ce = ClusteringEngine(uowf, graph, metrics=metrics)
        await ce.cluster_user(user)  # first run writes every member
        first_writes = metrics.snapshot().counters.get("clustering.member_writes_total", 0)
        assert first_writes >= 2  # at least one cluster's members written

        await ce.cluster_user(user)  # second run: cluster_id unchanged
        second_writes = metrics.snapshot().counters.get("clustering.member_writes_total", 0)
        # BEFORE: every member re-written each run. AFTER: zero new writes.
        assert second_writes == first_writes  # no additional writes
        await engine.dispose()

    _run(scenario)


# --- Phase 3: promotion deduplication --------------------------------------

def test_promotion_reinforces_instead_of_duplicating() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()
        pe = PromotionEngine(uowf, graph, InProcessEventDispatcher(),
                             PromotionConfig(min_occurrences=2))

        # batch 1: 3 recurring episodic -> 1 semantic created
        for _ in range(3):
            await _save(uowf, Memory.create(user_id=user, content="I am learning Rust",
                                            memory_type=MemoryType.EXPERIENCE))
        created_1 = await pe.promote_user(user)
        assert len(created_1) == 1
        semantic_id = created_1[0]

        async with uowf() as uow:
            sem_after_1 = await uow.memories.get_by_id(semantic_id)
        importance_1 = sem_after_1.score.importance

        # batch 2: 3 MORE recurring episodic of the SAME concept
        for _ in range(3):
            await _save(uowf, Memory.create(user_id=user, content="I am learning Rust",
                                            memory_type=MemoryType.EXPERIENCE))
        created_2 = await pe.promote_user(user)
        assert created_2 == []  # no NEW semantic memory

        async with uowf() as uow:
            all_mem = await uow.memories.list_for_analytics(user)
            sem_after_2 = await uow.memories.get_by_id(semantic_id)
        semantic = [m for m in all_mem if m.category is MemoryCategory.SEMANTIC
                    and m.memory_type is MemoryType.SKILL]
        assert len(semantic) == 1  # single representation, no duplicate
        assert sem_after_2.score.importance > importance_1  # importance increased
        # graph valid: PROMOTED_FROM edges for all 6 sources from the one semantic.
        promoted = [e for e in await graph.get_edges(str(semantic_id))
                    if e.edge_type is GraphEdgeType.PROMOTED_FROM]
        assert len(promoted) == 6
        await engine.dispose()

    _run(scenario)


# --- Phase 4: Neo4j cluster-edge cleanup -----------------------------------

def test_repeated_clustering_stabilizes_edge_count() -> None:
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
        await ce.cluster_user(user)
        after_first = await _count_edges(graph, GraphEdgeType.CLUSTER_MEMBER)
        for _ in range(5):
            await ce.cluster_user(user)
        after_many = await _count_edges(graph, GraphEdgeType.CLUSTER_MEMBER)
        assert after_first > 0
        assert after_many == after_first  # edge count stabilizes, no growth
        await engine.dispose()

    _run(scenario)


def test_cluster_cleanup_removes_stale_and_preserves_other_edges() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()

        # Cluster A (3 members) so it survives a member leaving; representative is
        # the lexicographically-smallest id, which we pin to stay in A.
        rep_id = uuid4()
        keep_id = uuid4()
        leaver_id = uuid4()
        a_rep = Memory(id=rep_id, user_id=user, content="alpha alpha shared topic one",
                       memory_type=MemoryType.FACT)
        a_keep = Memory(id=keep_id, user_id=user, content="alpha alpha shared topic two",
                        memory_type=MemoryType.FACT)
        a_leaver = Memory(id=leaver_id, user_id=user, content="alpha alpha shared topic three",
                          memory_type=MemoryType.FACT)
        for m in (a_rep, a_keep, a_leaver):
            await _save(uowf, m)

        ce = ClusteringEngine(uowf, graph)
        await ce.cluster_user(user)
        before = await _count_edges(graph, GraphEdgeType.CLUSTER_MEMBER)
        assert before >= 2  # rep -> {keep, leaver}

        # Preserve a non-cluster edge (e.g. PROMOTED_FROM) to prove it is kept.
        await graph.create_edge(GraphEdge(
            source_id=str(rep_id), target_id=str(keep_id),
            edge_type=GraphEdgeType.PROMOTED_FROM, weight=1.0, properties={}))

        # The leaver changes topic entirely -> drops out of cluster A.
        async with uowf() as uow:
            m = await uow.memories.get_by_id(leaver_id)
            m.update_content("zzz unrelated solitary subject qqq")
            await uow.memories.update(m)
            await uow.commit()

        await ce.cluster_user(user)
        cluster_edges = [e for e in graph._edges.values()
                         if e.edge_type is GraphEdgeType.CLUSTER_MEMBER]
        # stale edge to the leaver removed.
        assert all(str(leaver_id) not in (e.source_id, e.target_id) for e in cluster_edges)
        # valid edges retained (rep -> keep still present).
        assert any(e.source_id == str(rep_id) and e.target_id == str(keep_id)
                   for e in cluster_edges)
        # other edge type preserved.
        promoted = [e for e in await graph.get_edges(str(rep_id))
                    if e.edge_type is GraphEdgeType.PROMOTED_FROM]
        assert len(promoted) == 1
        await engine.dispose()

    _run(scenario)
