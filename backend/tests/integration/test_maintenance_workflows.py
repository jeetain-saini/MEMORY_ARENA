"""Integration tests for Stage 11 workflow orchestration.

Wires the maintenance workflows the way the lifespan does — the inference event
handler on a dispatcher, and the sweep/summary jobs on the InProcessScheduler —
and exercises both the event-driven and scheduled paths end-to-end against SQLite
and an in-memory graph. Offline; no real datastores.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import TypeVar
from uuid import UUID

from app.application.dto.graph_dto import GraphEdgeType
from app.application.services.maintenance.inference_event_handler import InferenceEventHandler
from app.application.services.maintenance.memory_summary_service import MemorySummaryService
from app.application.services.maintenance.relationship_inference_service import (
    RelationshipInferenceService,
)
from app.application.services.maintenance.summary_refresh_job import SummaryRefreshJob
from app.application.services.maintenance.sweeps import (
    ArchivalSweepJob,
    DecaySweepJob,
    PromotionSweepJob,
)
from app.application.services.memory_intelligence_service import MemoryIntelligenceService
from app.domain.entities.memory import Memory
from app.domain.entities.memory_score import MemoryScore
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from app.infrastructure.llm.in_process_maintenance_processor import (
    InProcessMaintenanceJobProcessor,
)
from app.infrastructure.scheduler.in_process_scheduler import InProcessScheduler
from app.infrastructure.summaries.deterministic_summary_generator import (
    DeterministicSummaryGenerator,
)
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

    dispatcher = InProcessEventDispatcher()

    def intelligence() -> MemoryIntelligenceService:
        return MemoryIntelligenceService(uow_factory(), dispatcher)

    return engine, uow_factory, dispatcher, intelligence, user


async def _save(uow_factory, user, content, mtype, *, score=None) -> Memory:
    memory = Memory.create(user_id=user, content=content, memory_type=mtype, score=score)
    async with uow_factory() as uow:
        await uow.memories.save(memory)
        await uow.commit()
    return memory


def test_memory_created_triggers_inference_workflow() -> None:
    async def scenario() -> None:
        engine, uow_factory, dispatcher, _intel, user = await _ctx()
        repo = InMemoryGraphRepository()
        await _save(uow_factory, user, "the analytics platform project uses python", MemoryType.SKILL)
        project = await _save(uow_factory, user, "python powers the analytics platform project", MemoryType.PROJECT)

        # Wire inference exactly like the lifespan does.
        service = RelationshipInferenceService(uow_factory, repo)
        processor = InProcessMaintenanceJobProcessor(service.process)
        InferenceEventHandler(processor).register(dispatcher)

        await dispatcher.dispatch(project.pull_events())  # MemoryCreated
        await processor.drain()

        edges = await repo.get_edges(str(project.id))
        assert any(e.edge_type is GraphEdgeType.DEPENDS_ON for e in edges)
        await engine.dispose()

    _run(scenario)


def test_scheduler_runs_all_maintenance_jobs() -> None:
    async def scenario() -> None:
        engine, uow_factory, dispatcher, intelligence, user = await _ctx()

        promote_me = await _save(
            uow_factory, user, "very valuable", MemoryType.FACT,
            score=MemoryScore(0.9, 0.9, 0.9, 0.9, 0.9),
        )
        await _save(uow_factory, user, "ship the platform", MemoryType.PROJECT)

        future = lambda: datetime.now(timezone.utc) + timedelta(days=10)  # noqa: E731
        summary_service = MemorySummaryService(uow_factory, DeterministicSummaryGenerator())

        scheduler = InProcessScheduler()
        scheduler.register(DecaySweepJob(uow_factory, intelligence, now_fn=future), cron="0 3 * * *")
        scheduler.register(ArchivalSweepJob(uow_factory, intelligence, now_fn=future), cron="0 4 * * *")
        scheduler.register(PromotionSweepJob(uow_factory, intelligence), cron="0 5 * * *")
        scheduler.register(SummaryRefreshJob(uow_factory, summary_service), cron="0 6 * * *")

        assert set(scheduler.jobs()) == {"decay_sweep", "archival_sweep", "promotion_sweep", "summary_refresh"}
        await scheduler.run_all()

        async with uow_factory() as uow:
            promoted = await uow.memories.get_by_id(promote_me.id)
            summary = await uow.summaries.get(user, MemoryType.PROJECT)
        assert promoted is not None and promoted.is_promoted  # promotion sweep ran
        assert summary is not None and "platform" in summary.summary_text  # summary refresh ran
        await engine.dispose()

    _run(scenario)


def test_scheduler_run_job_triggers_single_workflow() -> None:
    async def scenario() -> None:
        engine, uow_factory, dispatcher, intelligence, user = await _ctx()
        memory = await _save(
            uow_factory, user, "promote me", MemoryType.FACT,
            score=MemoryScore(0.9, 0.9, 0.9, 0.9, 0.9),
        )
        scheduler = InProcessScheduler()
        scheduler.register(PromotionSweepJob(uow_factory, intelligence), cron="0 5 * * *")

        await scheduler.run_job("promotion_sweep")
        async with uow_factory() as uow:
            stored = await uow.memories.get_by_id(memory.id)
        assert stored is not None and stored.is_promoted
        await engine.dispose()

    _run(scenario)


def test_decay_then_archival_workflow_sequence() -> None:
    async def scenario() -> None:
        engine, uow_factory, dispatcher, intelligence, user = await _ctx()
        memory = await _save(
            uow_factory, user, "low value idle", MemoryType.FACT,
            score=MemoryScore(0.1, 0.1, 0.0, 0.1, 0.1),
        )
        future = lambda: datetime.now(timezone.utc) + timedelta(days=40)  # noqa: E731

        await DecaySweepJob(uow_factory, intelligence, now_fn=future).run_sweep()
        await ArchivalSweepJob(uow_factory, intelligence, now_fn=future).run_sweep()

        async with uow_factory() as uow:
            stored = await uow.memories.get_by_id(memory.id)
        assert stored is not None and stored.status is MemoryStatus.ARCHIVED
        await engine.dispose()

    _run(scenario)
