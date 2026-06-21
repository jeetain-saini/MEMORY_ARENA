"""CLI: seed demo data into the configured database.

    cd backend && PYTHONPATH=. python scripts/seed_demo.py

Connects the configured datastore, optionally creates the schema (SQLite via
``AUTO_CREATE_SCHEMA``), and runs the idempotent demo seed. For a full demo
(embeddings + graph populated), prefer ``SEED_DEMO_ON_STARTUP=true`` so seeding
runs inside the app lifespan with every event handler registered; this CLI seeds
users/memories/summaries for manual/persistent (e.g. Neon) setups.
"""

from __future__ import annotations

import asyncio


async def _main() -> None:
    from app.core.config import get_settings
    from app.infrastructure.database.postgres import postgres_manager
    from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
    from app.infrastructure.events.in_process_dispatcher import in_process_dispatcher
    from app.infrastructure.seed.demo_seed import seed_demo
    from app.infrastructure.summaries.deterministic_summary_generator import (
        DeterministicSummaryGenerator,
    )

    settings = get_settings()
    await postgres_manager.connect(settings)
    if settings.auto_create_schema:
        from app.infrastructure.database import models as _models  # noqa: F401
        from app.infrastructure.database.base import Base

        async with postgres_manager.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    result = await seed_demo(
        lambda: SQLAlchemyUnitOfWork(postgres_manager.sessionmaker),
        in_process_dispatcher,
        summary_generator=DeterministicSummaryGenerator(),
    )
    print(f"seeded: {result}")
    await postgres_manager.disconnect()


if __name__ == "__main__":
    asyncio.run(_main())
