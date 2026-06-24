"""Summaries refresh immediately on memory writes (no maintenance-job dependency).

A MemoryCreated event triggers a summary refresh; an archive/supersede drops the
old memory so the summary reflects the latest truth.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.application.dto.memory_dto import CreateMemoryRequest
from app.application.services.maintenance.config import MaintenanceConfig
from app.application.services.maintenance.memory_summary_service import MemorySummaryService
from app.application.services.maintenance.summary_event_handler import (
    SummaryRefreshEventHandler,
)
from app.application.use_cases.memory_use_cases_impl import CreateMemoryUseCaseImpl
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from app.infrastructure.summaries.deterministic_summary_generator import (
    DeterministicSummaryGenerator,
)
from tests.integration._db import make_engine


def test_summary_created_on_memory_write() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        sf = create_session_factory(engine)
        uowf = lambda: SQLAlchemyUnitOfWork(sf)
        dispatcher = InProcessEventDispatcher()
        summary_service = MemorySummaryService(
            uowf, DeterministicSummaryGenerator(),
            MaintenanceConfig(summary_scopes=tuple(MemoryType)),
        )
        SummaryRefreshEventHandler(summary_service).register(dispatcher)

        user = uuid4()
        create = CreateMemoryUseCaseImpl(uowf(), dispatcher)
        await create.execute(CreateMemoryRequest(
            user_id=user, content="My favorite language is Rust",
            memory_type=MemoryType.PREFERENCE, metadata={}))

        # No maintenance job ran — the write itself refreshed the summary.
        summaries = await summary_service.list_for_user(user)
        assert len(summaries) >= 1
        assert any("rust" in s.summary_text.lower() for s in summaries)
        await engine.dispose()

    asyncio.run(scenario())
