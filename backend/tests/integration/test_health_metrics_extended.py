"""Integration test for Stage 16 extended health metrics (SQLite + in-memory graph)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.application.dto.graph_dto import GraphEdge, GraphEdgeType, GraphNode, NodeType
from app.application.services.observability.memory_health_service import MemoryHealthService
from app.domain.entities.memory import Memory
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from app.domain.value_objects.memory_type import MemoryType
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


def test_extended_metrics_contradictions_superseded_types_importance_confidence() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uow = SQLAlchemyUnitOfWork(create_session_factory(engine))
        graph = InMemoryGraphRepository()

        mems = [
            Memory.create(user_id=user, content="I use Python", memory_type=MemoryType.FACT),
            Memory.create(user_id=user, content="I do not use Python", memory_type=MemoryType.FACT),
            Memory.create(user_id=user, content="I prefer dark mode", memory_type=MemoryType.PREFERENCE),
            Memory.create(user_id=user, content="Ship by Q3", memory_type=MemoryType.GOAL),
        ]
        async with uow:
            for m in mems:
                await uow.memories.save(m)
            await uow.commit()

        # graph nodes + a CONTRADICTS and a SUPERSEDES edge
        for m in mems:
            await graph.create_node(
                GraphNode(node_id=str(m.id), node_type=NodeType.FACT, label=m.content,
                          properties={"user_id": str(user)})
            )
        await graph.create_edge(GraphEdge(str(mems[1].id), str(mems[0].id), GraphEdgeType.CONTRADICTS))
        await graph.create_edge(GraphEdge(str(mems[0].id), str(mems[1].id), GraphEdgeType.SUPERSEDES))

        health = await MemoryHealthService(uow, graph).get_health(user_id=user)

        assert health.contradiction_count == 1
        assert health.superseded_count == 1
        assert health.type_distribution == {"fact": 2, "preference": 1, "goal": 1}
        assert 0.0 < health.average_importance <= 1.0
        assert 0.0 < health.average_confidence <= 1.0
        await engine.dispose()

    _run(scenario)
