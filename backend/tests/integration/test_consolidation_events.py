"""Integration: ConsolidationEventHandler + InProcessConsolidationJobProcessor.

Verifies the full event-driven wiring: MemoryCreated → handler → job submitted
→ drain → service ran.  Uses a spy service instead of the full
PersistentConsolidationService to isolate the wiring logic.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.application.interfaces.consolidation_job_processor import ConsolidationJob
from app.application.services.consolidation.consolidation_event_handler import (
    ConsolidationEventHandler,
)
from app.domain.events.memory_events import MemoryCreated
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from app.infrastructure.llm.in_process_consolidation_processor import (
    InProcessConsolidationJobProcessor,
)


def _run(coro):
    return asyncio.run(coro)


def test_memory_created_triggers_consolidation_job() -> None:
    """MemoryCreated → handler → submit → drain → runner called once."""

    async def scenario() -> None:
        ran: list[ConsolidationJob] = []

        async def runner(job: ConsolidationJob) -> None:
            ran.append(job)

        processor = InProcessConsolidationJobProcessor(runner)
        dispatcher = InProcessEventDispatcher()
        ConsolidationEventHandler(processor).register(dispatcher)

        memory_id = uuid4()
        user_id = uuid4()
        event = MemoryCreated(
            memory_id=memory_id,
            user_id=user_id,
            memory_type=MemoryType.FACT,
        )
        await dispatcher.dispatch([event])
        await processor.drain()

        assert len(ran) == 1
        assert ran[0].memory_id == memory_id
        assert ran[0].user_id == user_id

    _run(scenario())


def test_multiple_memory_created_events_submit_multiple_jobs() -> None:
    async def scenario() -> None:
        ran: list[ConsolidationJob] = []

        async def runner(job: ConsolidationJob) -> None:
            ran.append(job)

        processor = InProcessConsolidationJobProcessor(runner)
        dispatcher = InProcessEventDispatcher()
        ConsolidationEventHandler(processor).register(dispatcher)

        events = [
            MemoryCreated(memory_id=uuid4(), user_id=uuid4(), memory_type=MemoryType.FACT)
            for _ in range(3)
        ]
        await dispatcher.dispatch(events)
        await processor.drain()

        assert len(ran) == 3

    _run(scenario())


def test_handler_does_not_subscribe_to_other_events() -> None:
    """ConsolidationEventHandler only reacts to MemoryCreated, not other event types."""

    async def scenario() -> None:
        ran: list[ConsolidationJob] = []

        async def runner(job: ConsolidationJob) -> None:
            ran.append(job)

        processor = InProcessConsolidationJobProcessor(runner)
        dispatcher = InProcessEventDispatcher()
        ConsolidationEventHandler(processor).register(dispatcher)

        # Dispatch a non-MemoryCreated event.
        from app.domain.events.memory_events import MemoryArchived
        await dispatcher.dispatch([MemoryArchived(memory_id=uuid4(), user_id=uuid4())])
        await processor.drain()

        assert ran == []

    _run(scenario())


def test_drain_after_no_events_does_not_raise() -> None:
    async def scenario() -> None:
        async def runner(job: ConsolidationJob) -> None:
            pass

        processor = InProcessConsolidationJobProcessor(runner)
        await processor.drain()  # nothing submitted — must not raise

    _run(scenario())
