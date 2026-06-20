"""Integration tests for RelationshipInferenceService (SQLite + in-memory graph)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from app.application.dto.graph_dto import GraphEdgeType
from app.application.interfaces.maintenance_job_processor import InferenceJob
from app.application.services.graph.config import GraphConfig
from app.application.services.graph.relationship_service import GraphRelationshipService
from app.application.services.graph.sync_service import GraphSyncService
from app.application.services.maintenance.config import MaintenanceConfig
from app.application.services.maintenance.inference_event_handler import InferenceEventHandler
from app.application.services.maintenance.relationship_inference_service import (
    RelationshipInferenceService,
)
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.llm.in_process_maintenance_processor import (
    InProcessMaintenanceJobProcessor,
)
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from app.domain.events.memory_events import MemoryCreated
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _ctx():
    engine = await make_engine()
    user = await seed_user(engine)
    factory = create_session_factory(engine)

    def uow_factory() -> SQLAlchemyUnitOfWork:
        return SQLAlchemyUnitOfWork(factory)

    return engine, uow_factory, user


async def _save(uow_factory, user: UUID, content: str, mtype: MemoryType) -> Memory:
    memory = Memory.create(user_id=user, content=content, memory_type=mtype)
    async with uow_factory() as uow:
        await uow.memories.save(memory)
        await uow.commit()
    return memory


# Two memories that share most entities → high Jaccard, PROJECT->SKILL ⇒ DEPENDS_ON.
_PROJECT = "python powers the analytics platform project"
_SKILL = "the analytics platform project uses python"


def test_infers_and_writes_edge() -> None:
    async def scenario() -> None:
        engine, uow_factory, user = await _ctx()
        repo = InMemoryGraphRepository()
        await _save(uow_factory, user, _SKILL, MemoryType.SKILL)
        project = await _save(uow_factory, user, _PROJECT, MemoryType.PROJECT)

        service = RelationshipInferenceService(uow_factory, repo)
        created = await service.infer_for_memory(project.id)

        assert created == 1
        edges = await repo.get_edges(str(project.id))
        assert any(e.edge_type is GraphEdgeType.DEPENDS_ON for e in edges)
        await engine.dispose()

    _run(scenario)


def test_duplicate_edges_prevented() -> None:
    async def scenario() -> None:
        engine, uow_factory, user = await _ctx()
        repo = InMemoryGraphRepository()
        await _save(uow_factory, user, _SKILL, MemoryType.SKILL)
        project = await _save(uow_factory, user, _PROJECT, MemoryType.PROJECT)
        service = RelationshipInferenceService(uow_factory, repo)

        first = await service.infer_for_memory(project.id)
        second = await service.infer_for_memory(project.id)
        assert first == 1
        assert second == 0  # dedup: existing edge is not recreated
        assert len(await repo.get_edges(str(project.id))) == 1
        await engine.dispose()

    _run(scenario)


def test_confidence_threshold_gates_writes() -> None:
    async def scenario() -> None:
        engine, uow_factory, user = await _ctx()
        repo = InMemoryGraphRepository()
        await _save(uow_factory, user, _SKILL, MemoryType.SKILL)
        project = await _save(uow_factory, user, _PROJECT, MemoryType.PROJECT)
        service = RelationshipInferenceService(
            uow_factory, repo, config=MaintenanceConfig(inference_confidence_threshold=0.99)
        )
        created = await service.infer_for_memory(project.id)
        assert created == 0
        await engine.dispose()

    _run(scenario)


def test_unrelated_memories_no_edge() -> None:
    async def scenario() -> None:
        engine, uow_factory, user = await _ctx()
        repo = InMemoryGraphRepository()
        await _save(uow_factory, user, "cats love fresh fish daily", MemoryType.FACT)
        project = await _save(uow_factory, user, _PROJECT, MemoryType.PROJECT)
        service = RelationshipInferenceService(uow_factory, repo)
        created = await service.infer_for_memory(project.id)
        assert created == 0
        await engine.dispose()

    _run(scenario)


def test_inferred_edge_survives_graph_sync() -> None:
    async def scenario() -> None:
        engine, uow_factory, user = await _ctx()
        repo = InMemoryGraphRepository()
        await _save(uow_factory, user, _SKILL, MemoryType.SKILL)
        project = await _save(uow_factory, user, _PROJECT, MemoryType.PROJECT)

        config = GraphConfig()
        service = RelationshipInferenceService(uow_factory, repo, graph_config=config)
        await service.infer_for_memory(project.id)
        assert any(e.edge_type is GraphEdgeType.DEPENDS_ON for e in await repo.get_edges(str(project.id)))

        # A subsequent graph sync must NOT delete the inferred DEPENDS_ON edge.
        sync = GraphSyncService(uow_factory, repo, GraphRelationshipService(config), config)
        await sync.sync_memory(project.id)
        edges_after = await repo.get_edges(str(project.id))
        assert any(e.edge_type is GraphEdgeType.DEPENDS_ON for e in edges_after)
        await engine.dispose()

    _run(scenario)


def test_event_handler_submits_inference_job() -> None:
    async def scenario() -> None:
        engine, uow_factory, user = await _ctx()
        repo = InMemoryGraphRepository()
        await _save(uow_factory, user, _SKILL, MemoryType.SKILL)
        project = await _save(uow_factory, user, _PROJECT, MemoryType.PROJECT)

        service = RelationshipInferenceService(uow_factory, repo)
        processor = InProcessMaintenanceJobProcessor(service.process)
        dispatcher = InProcessEventDispatcher()
        InferenceEventHandler(processor).register(dispatcher)

        await dispatcher.dispatch([MemoryCreated(memory_id=project.id, user_id=user, memory_type=MemoryType.PROJECT)])
        await processor.drain()

        assert any(e.edge_type is GraphEdgeType.DEPENDS_ON for e in await repo.get_edges(str(project.id)))
        await engine.dispose()

    _run(scenario)
