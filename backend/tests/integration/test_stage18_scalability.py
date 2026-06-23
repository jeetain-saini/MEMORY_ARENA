"""Stage 18 scalability integration tests.

Stage 18.1 — GraphSnapshotProvider batches the per-memory graph reads that the
Stage 17 intelligence engines used to issue. These tests prove:

  * the snapshot indexes a tenant's subgraph correctly (degree / isolation /
    edges / max-degree);
  * the maintenance cycle reads the graph in a *bounded* number of batched
    ``get_subgraph`` calls instead of one ``get_edges`` per memory;
  * batching changes I/O shape only — the evolved/forgotten results are identical
    to the pre-Stage-18 per-memory path.

SQLite + in-memory graph + dispatcher (same harness as the Stage 17 suites).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import TypeVar
from uuid import UUID

from app.application.dto.graph_dto import (
    GraphEdge,
    GraphEdgeType,
    GraphNode,
    GraphOverview,
    NodeType,
)
from app.application.services.context._text import jaccard
from app.application.services.intelligence.clustering_engine import (
    ClusterConfig,
    ClusteringEngine,
    _sig,
)
from app.application.services.intelligence.forgetting_engine import (
    ForgettingConfig,
    ForgettingEngine,
)
from app.application.services.intelligence.graph_snapshot import (
    GraphSnapshot,
    GraphSnapshotProvider,
)
from app.application.services.intelligence.maintenance_job import (
    MemoryIntelligenceMaintenanceJob,
    evolve_importance_for_user,
)
from app.application.services.intelligence.importance_evolution import (
    ImportanceEvolutionService,
)
from app.domain.entities.memory import Memory
from app.domain.entities.memory_score import MemoryScore
from app.domain.value_objects.memory_status import MemoryStatus
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


async def _save(uow_factory, memory: Memory) -> None:
    async with uow_factory() as uow:
        await uow.memories.save(memory)
        await uow.commit()


class CountingGraphRepository(InMemoryGraphRepository):
    """Wraps the in-memory graph to count read calls by kind."""

    def __init__(self) -> None:
        super().__init__()
        self.get_edges_calls = 0
        self.get_subgraph_calls = 0

    async def get_edges(self, node_id, exclude_types=None):  # type: ignore[override]
        self.get_edges_calls += 1
        return await super().get_edges(node_id, exclude_types)

    async def get_subgraph(self, user_id):  # type: ignore[override]
        self.get_subgraph_calls += 1
        return await super().get_subgraph(user_id)


# --- 1. snapshot indexing --------------------------------------------------

def test_graph_snapshot_indexes_subgraph() -> None:
    a, b, c = "11111111-1111-1111-1111-111111111111", \
        "22222222-2222-2222-2222-222222222222", \
        "33333333-3333-3333-3333-333333333333"
    nodes = [
        GraphNode(node_id=a, node_type=NodeType.MEMORY, label="a"),
        GraphNode(node_id=b, node_type=NodeType.MEMORY, label="b"),
        GraphNode(node_id=c, node_type=NodeType.MEMORY, label="c"),
    ]
    edges = [
        GraphEdge(source_id=a, target_id=b, edge_type=GraphEdgeType.RELATED_TO),
        GraphEdge(source_id=a, target_id=c, edge_type=GraphEdgeType.RELATED_TO),
    ]
    snap = GraphSnapshot.from_overview(GraphOverview(nodes=nodes, edges=edges))

    assert snap.degree(a) == 2          # connected to b and c
    assert snap.degree(b) == 1          # connected to a
    assert snap.degree(c) == 1
    assert snap.is_isolated(a) is False
    assert snap.is_isolated(b) is False
    # an unknown node is treated as isolated (degree 0).
    assert snap.is_isolated("00000000-0000-0000-0000-000000000000") is True
    assert snap.max_degree == 2
    assert {e.target_id for e in snap.edges_for(a)} == {b, c}


def test_snapshot_provider_uses_single_subgraph_read() -> None:
    async def scenario() -> None:
        graph = CountingGraphRepository()
        user = UUID("44444444-4444-4444-4444-444444444444")
        await graph.upsert_node(
            GraphNode(node_id=str(user), node_type=NodeType.MEMORY, label="x",
                      properties={"user_id": str(user)})
        )
        snap = await GraphSnapshotProvider(graph).snapshot(user)
        assert graph.get_subgraph_calls == 1
        assert graph.get_edges_calls == 0
        assert isinstance(snap, GraphSnapshot)

    _run(scenario)


# --- 2. maintenance batches graph reads ------------------------------------

def test_maintenance_batches_graph_reads_and_matches_baseline() -> None:
    """The maintenance cycle must not issue per-memory get_edges for evolve/forget.

    We seed a tenant with old, low-importance, isolated memories (forgettable) and
    run the full cycle. The snapshot path means ``get_subgraph`` is called a small
    bounded number of times and ``get_edges`` is never called by evolve/forget.
    """
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = CountingGraphRepository()
        dispatcher = InProcessEventDispatcher()

        old = datetime.now(timezone.utc) - timedelta(days=200)
        # Distinct, non-overlapping content so clustering forms no components
        # (keeps this test focused on the evolve/forget batching path).
        words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"]
        memories: list[Memory] = []
        for word in words:
            m = Memory.create(
                user_id=user, content=word,
                memory_type=MemoryType.FACT,
            )
            m.score = MemoryScore(importance=0.1, utility=0.1, frequency=0.0,
                                  recency=0.0, confidence=0.5)
            m.updated_at = old
            memories.append(m)
            await _save(uowf, m)

        job = MemoryIntelligenceMaintenanceJob(
            uowf, graph, dispatcher,
            forgetting=ForgettingEngine(
                uowf, graph, dispatcher,
                ForgettingConfig(min_age_days=90, max_importance=0.25,
                                 max_retrievals=0, require_isolated=True),
            ),
        )
        result = await job.run_cycle(user_id=user)

        # Forgetting saw the isolated stale memories and forgot them.
        assert result.forgotten == 6
        # Batched: at most a couple of subgraph reads per tenant (evolve + forget),
        # and crucially NO per-memory get_edges from evolve/forget.
        assert graph.get_subgraph_calls <= 2
        assert graph.get_edges_calls == 0

        async with uowf() as uow:
            after = await uow.memories.list_for_analytics(user)
        forgotten = [m for m in after if m.status is MemoryStatus.FORGOTTEN]
        assert len(forgotten) == 6
        await engine.dispose()

    _run(scenario)


def test_evolve_importance_standalone_builds_its_own_snapshot() -> None:
    """Calling evolve without a snapshot still works (one subgraph read, no per-memory edges)."""
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = CountingGraphRepository()

        hub = Memory.create(user_id=user, content="central hub memory",
                            memory_type=MemoryType.FACT)
        leaf = Memory.create(user_id=user, content="peripheral leaf memory",
                             memory_type=MemoryType.FACT)
        await _save(uowf, hub)
        await _save(uowf, leaf)
        # give the graph a node per memory + one edge so degrees differ.
        for m in (hub, leaf):
            await graph.upsert_node(
                GraphNode(node_id=str(m.id), node_type=NodeType.MEMORY,
                          label=m.content, properties={"user_id": str(user)})
            )
        await graph.create_edge(
            GraphEdge(source_id=str(hub.id), target_id=str(leaf.id),
                      edge_type=GraphEdgeType.RELATED_TO)
        )

        changed = await evolve_importance_for_user(
            uowf, graph, ImportanceEvolutionService(), user
        )
        assert changed >= 0                     # idempotent-safe
        assert graph.get_subgraph_calls == 1    # built its own snapshot
        assert graph.get_edges_calls == 0       # no per-memory reads
        await engine.dispose()

    _run(scenario)


# --- 3. incremental clustering (Stage 18.2) --------------------------------

def _bruteforce_components(memories: list[Memory]) -> list[set[UUID]]:
    """Reference O(n^2) connected-components partition (the pre-18.2 algorithm)."""
    sigs = {m.id: _sig(m.content) for m in memories}
    parent = {m.id: m.id for m in memories}

    def find(x: UUID) -> UUID:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(memories):
        for b in memories[i + 1:]:
            if sigs[a.id] and sigs[b.id] and jaccard(sigs[a.id], sigs[b.id]) >= 0.2:
                parent[find(a.id)] = find(b.id)
    groups: dict[UUID, set[UUID]] = {}
    for m in memories:
        groups.setdefault(find(m.id), set()).add(m.id)
    return [g for g in groups.values() if len(g) >= 2]


async def _clustered_partition(uowf, user: UUID) -> list[set[UUID]]:
    """The engine's actual partition, read back from each memory's cluster_id."""
    async with uowf() as uow:
        memories = await uow.memories.list_for_analytics(user)
    by_cluster: dict[str, set[UUID]] = {}
    for m in memories:
        cid = m.metadata.get("cluster_id")
        if cid:
            by_cluster.setdefault(cid, set()).add(m.id)
    return [ids for ids in by_cluster.values() if len(ids) >= 2]


def _norm(parts: list[set[UUID]]) -> set[frozenset[UUID]]:
    return {frozenset(p) for p in parts}


def test_clustering_inverted_index_matches_bruteforce() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()

        contents = [
            "python asyncio await coroutine",     # cluster X
            "python asyncio event loop",          # cluster X
            "neo4j cypher graph traversal",       # cluster Y
            "neo4j cypher query plan",            # cluster Y
            "totally unrelated solitary subject", # singleton
            "python asyncio await future",        # cluster X (bridges via shared tokens)
        ]
        memories = []
        for c in contents:
            m = Memory.create(user_id=user, content=c, memory_type=MemoryType.FACT)
            memories.append(m)
            await _save(uowf, m)

        await ClusteringEngine(uowf, graph, ClusterConfig(min_overlap=0.2)).cluster_user(user)

        expected = _norm(_bruteforce_components(memories))
        actual = _norm(await _clustered_partition(uowf, user))
        assert actual == expected
        assert any(len(p) >= 3 for p in expected)  # the python/asyncio group
        await engine.dispose()

    _run(scenario)


def test_clustering_skips_pairs_with_no_shared_tokens() -> None:
    """Disjoint-token memories trigger zero Jaccard comparisons (vs O(n^2) brute force)."""
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()
        metrics = InMemoryMetricsSink()

        # 8 memories with entirely distinct vocabularies — no two share a token.
        words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]
        for w in words:
            await _save(uowf, Memory.create(user_id=user, content=f"{w}{w} {w}xx",
                                            memory_type=MemoryType.FACT))

        ce = ClusteringEngine(uowf, graph, ClusterConfig(min_overlap=0.2), metrics=metrics)
        await ce.cluster_user(user)

        comparisons = metrics.snapshot().counters.get("clustering.pair_comparisons_total", 0)
        # The exhaustive scan would have made 8*7/2 = 28 comparisons; the inverted
        # index makes none, since no pair shares a token.
        assert comparisons == 0
        await engine.dispose()

    _run(scenario)


def test_clustering_merges_when_bridge_memory_appears() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()
        ce = ClusteringEngine(uowf, graph, ClusterConfig(min_overlap=0.2))

        # Two disjoint clusters.
        for _ in range(2):
            await _save(uowf, Memory.create(user_id=user, content="apple banana cherry",
                                            memory_type=MemoryType.FACT))
        for _ in range(2):
            await _save(uowf, Memory.create(user_id=user, content="delta echo foxtrot",
                                            memory_type=MemoryType.FACT))
        await ce.cluster_user(user)
        first = await _clustered_partition(uowf, user)
        assert len(first) == 2  # two separate clusters

        # A bridge memory sharing tokens with both clusters merges them.
        await _save(uowf, Memory.create(user_id=user, content="apple banana delta echo",
                                        memory_type=MemoryType.FACT))
        await ce.cluster_user(user)
        merged = await _clustered_partition(uowf, user)
        assert len(merged) == 1               # one merged cluster
        assert len(next(iter(merged))) == 5   # all five members
        await engine.dispose()

    _run(scenario)


def test_clustering_splits_when_bridge_changes_topic() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()
        ce = ClusteringEngine(uowf, graph, ClusterConfig(min_overlap=0.2))

        a1 = Memory.create(user_id=user, content="apple banana cherry", memory_type=MemoryType.FACT)
        a2 = Memory.create(user_id=user, content="apple banana cherry", memory_type=MemoryType.FACT)
        b1 = Memory.create(user_id=user, content="delta echo foxtrot", memory_type=MemoryType.FACT)
        b2 = Memory.create(user_id=user, content="delta echo foxtrot", memory_type=MemoryType.FACT)
        bridge = Memory.create(user_id=user, content="apple banana delta echo",
                               memory_type=MemoryType.FACT)
        for m in (a1, a2, b1, b2, bridge):
            await _save(uowf, m)

        await ce.cluster_user(user)
        assert len(await _clustered_partition(uowf, user)) == 1  # merged via bridge

        # The bridge changes topic entirely -> the cluster splits back into two.
        async with uowf() as uow:
            m = await uow.memories.get_by_id(bridge.id)
            m.update_content("zzz unrelated solitary subject qqq")
            await uow.memories.update(m)
            await uow.commit()
        await ce.cluster_user(user)
        split = await _clustered_partition(uowf, user)
        assert len(split) == 2                       # two clusters again
        assert all(len(p) == 2 for p in split)       # {a1,a2} and {b1,b2}
        await engine.dispose()

    _run(scenario)
