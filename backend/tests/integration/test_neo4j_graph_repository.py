"""Live integration tests for Neo4jGraphRepository.

These exercise the Cypher-backed backend against a real Neo4j server. They
**skip automatically** when no server is reachable (driver missing, wrong
credentials, or nothing listening), so the offline/CI suite stays green without
Neo4j. To run them, bring up Neo4j (e.g. ``docker compose up neo4j``) with
credentials matching the NEO4J_* settings.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

import pytest

pytest.importorskip("neo4j")

os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USERNAME", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "secret")
os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")

from app.application.dto.graph_dto import GraphEdge, GraphEdgeType, GraphNode, NodeType  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.infrastructure.graph.neo4j import Neo4jManager  # noqa: E402
from app.infrastructure.graph.neo4j_graph_repository import Neo4jGraphRepository  # noqa: E402

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _connect_or_skip() -> Neo4jManager:
    get_settings.cache_clear()
    manager = Neo4jManager()
    try:
        await manager.connect(get_settings())
    except Exception as exc:  # noqa: BLE001 - any failure => no live server
        pytest.skip(f"Neo4j not available: {exc}")
    return manager


def _node(node_id: str, content: str = "python") -> GraphNode:
    return GraphNode(
        node_id=node_id, node_type=NodeType.FACT, label=content,
        properties={"content": content, "user_id": "u1"},
    )


def test_node_roundtrip_and_delete() -> None:
    async def scenario() -> None:
        manager = await _connect_or_skip()
        repo = Neo4jGraphRepository(manager)
        nid = f"test-{uuid4()}"
        try:
            await repo.upsert_node(_node(nid))
            fetched = await repo.get_node(nid)
            assert fetched is not None and fetched.node_id == nid
            await repo.delete_node(nid)
            assert await repo.get_node(nid) is None
        finally:
            await repo.delete_node(nid)
            await manager.disconnect()

    _run(scenario)


def test_edge_create_and_neighbors() -> None:
    async def scenario() -> None:
        manager = await _connect_or_skip()
        repo = Neo4jGraphRepository(manager)
        a, b = f"test-{uuid4()}", f"test-{uuid4()}"
        try:
            await repo.upsert_node(_node(a))
            await repo.upsert_node(_node(b))
            await repo.create_edge(GraphEdge(a, b, GraphEdgeType.RELATED_TO, weight=0.5))

            neighbors = await repo.find_neighbors(a, depth=1)
            assert any(n.node_id == b for n in neighbors)

            edges = await repo.get_edges(a)
            assert any({e.source_id, e.target_id} == {a, b} for e in edges)
        finally:
            await repo.delete_node(a)
            await repo.delete_node(b)
            await manager.disconnect()

    _run(scenario)


def test_get_edges_reports_true_direction() -> None:
    async def scenario() -> None:
        manager = await _connect_or_skip()
        repo = Neo4jGraphRepository(manager)
        a, b = f"test-{uuid4()}", f"test-{uuid4()}"
        try:
            await repo.upsert_node(_node(a))
            await repo.upsert_node(_node(b))
            await repo.create_edge(GraphEdge(a, b, GraphEdgeType.RELATED_TO))

            # Querying from the target must still report source=a, target=b, so
            # the directional delete_edge can match the stored relationship.
            edges = await repo.get_edges(b)
            match = [e for e in edges if {e.source_id, e.target_id} == {a, b}]
            assert match and match[0].source_id == a and match[0].target_id == b

            await repo.delete_edge(match[0].source_id, match[0].target_id, match[0].edge_type)
            assert await repo.get_edges(a) == []
        finally:
            await repo.delete_node(a)
            await repo.delete_node(b)
            await manager.disconnect()

    _run(scenario)


def test_find_paths() -> None:
    async def scenario() -> None:
        manager = await _connect_or_skip()
        repo = Neo4jGraphRepository(manager)
        a, b, c = f"test-{uuid4()}", f"test-{uuid4()}", f"test-{uuid4()}"
        try:
            for nid in (a, b, c):
                await repo.upsert_node(_node(nid))
            await repo.create_edge(GraphEdge(a, b, GraphEdgeType.RELATED_TO))
            await repo.create_edge(GraphEdge(b, c, GraphEdgeType.RELATED_TO))

            paths = await repo.find_paths(a, c, max_depth=4)
            assert paths and any(p.length >= 2 for p in paths)
        finally:
            for nid in (a, b, c):
                await repo.delete_node(nid)
            await manager.disconnect()

    _run(scenario)
