"""Production-hardening tests (Phases 5-6):

* Phase 5 — background processing safety: no orphan tasks / leaks under load;
  the reactive promotion cascade terminates (no infinite loop).
* Phase 6 — observability: scheduler + maintenance metrics are recorded.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import TypeVar
from uuid import uuid4

from app.application.interfaces.intelligence_job_processor import IntelligenceJob
from app.application.interfaces.scheduler import ScheduledJob
from app.application.services.intelligence.clustering_engine import ClusteringEngine
from app.application.services.intelligence.intelligence_event_handler import (
    IntelligenceEventHandler,
)
from app.application.services.intelligence.maintenance_job import (
    MemoryIntelligenceMaintenanceJob,
)
from app.application.services.intelligence.promotion_engine import PromotionEngine
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_category import MemoryCategory
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from app.infrastructure.intelligence.in_process_processor import (
    InProcessIntelligenceJobProcessor,
)
from app.infrastructure.observability.in_memory_metrics import InMemoryMetricsSink
from app.infrastructure.scheduler.in_process_scheduler import InProcessScheduler
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


# --- Phase 5: 1000-event stress; task count stabilizes, no orphans ---------

def test_processor_no_orphan_tasks_under_1000_events() -> None:
    async def scenario() -> None:
        processed = 0

        async def runner(job: IntelligenceJob) -> None:
            nonlocal processed
            processed += 1

        proc = InProcessIntelligenceJobProcessor(runner)
        for _ in range(1000):
            await proc.submit(IntelligenceJob(user_id=uuid4()))
        await proc.drain()
        assert processed == 1000          # no lost events
        assert len(proc._tasks) == 0      # task count stabilizes -> no leak/orphans

    _run(scenario)


def test_reactive_promotion_cascade_terminates() -> None:
    """A MemoryCreated triggers promotion which itself dispatches MemoryCreated;
    prove it terminates and produces exactly one semantic memory (no runaway)."""

    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()
        dispatcher = InProcessEventDispatcher()
        promotion = PromotionEngine(uowf, graph, dispatcher)
        clustering = ClusteringEngine(uowf, graph)

        async def runner(job: IntelligenceJob) -> None:
            await promotion.promote_user(job.user_id)
            await clustering.cluster_user(job.user_id)

        processor = InProcessIntelligenceJobProcessor(runner)
        IntelligenceEventHandler(processor).register(dispatcher)

        for _ in range(3):
            await _save(uowf, Memory.create(user_id=user, content="I am learning Rust",
                                            memory_type=MemoryType.EXPERIENCE))
        mem = Memory.create(user_id=user, content="I am learning Rust",
                            memory_type=MemoryType.EXPERIENCE)
        await _save(uowf, mem)
        await dispatcher.dispatch(mem.pull_events())
        await asyncio.wait_for(processor.drain(), timeout=5.0)  # must not hang

        async with uowf() as uow:
            all_mem = await uow.memories.list_for_analytics(user)
        semantic = [m for m in all_mem if m.category is MemoryCategory.SEMANTIC
                    and m.memory_type is MemoryType.SKILL]
        assert len(semantic) == 1  # bounded: no duplicate-creation loop
        assert len(processor._tasks) == 0
        await engine.dispose()

    _run(scenario)


# --- Phase 6: observability -------------------------------------------------

def test_scheduler_records_job_metrics() -> None:
    async def scenario() -> None:
        metrics = InMemoryMetricsSink()
        now = datetime(2026, 6, 23, 2, 0, tzinfo=timezone.utc)

        class _OkJob(ScheduledJob):
            name = "ok"

            async def run(self) -> None:
                return None

        class _BadJob(ScheduledJob):
            name = "bad"

            async def run(self) -> None:
                raise RuntimeError("boom")

        sched = InProcessScheduler(metrics=metrics, clock=lambda: now)
        sched.register(_OkJob(), cron="0 2 * * *")
        sched.register(_BadJob(), cron="0 2 * * *")
        await sched.run_due(now)
        counters = metrics.snapshot().counters
        assert counters.get("scheduler.jobs_run_total") == 1
        assert counters.get("scheduler.jobs_failed_total") == 1
        assert "scheduler.job_duration_ms.ok" in metrics.snapshot().latencies

    _run(scenario)


def test_maintenance_job_records_outcome_metrics() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()
        metrics = InMemoryMetricsSink()
        for _ in range(3):
            await _save(uowf, Memory.create(user_id=user, content="learning LangGraph daily",
                                            memory_type=MemoryType.EXPERIENCE))
        job = MemoryIntelligenceMaintenanceJob(
            uowf, graph, InProcessEventDispatcher(), metrics=metrics
        )
        await job.run_cycle(user_id=user)
        counters = metrics.snapshot().counters
        assert counters.get("memories_promoted_total", 0) >= 1
        assert "memories_forgotten_total" in counters
        assert "memories_clustered_total" in counters
        await engine.dispose()

    _run(scenario)
