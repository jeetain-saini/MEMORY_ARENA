"""Phase 2: datastore health checks fail fast (never hang) on an outage.

Deterministic — no network. Each manager's ``health_check`` is wrapped in an
``asyncio.timeout`` bound, so a connection that hangs forever still resolves to
``False`` within the budget instead of blocking the /health endpoint or the
startup readiness loop.
"""

from __future__ import annotations

import asyncio
import time

from app.infrastructure.cache.redis import RedisManager
from app.infrastructure.database.postgres import PostgresManager
from app.infrastructure.graph.neo4j import Neo4jManager


class _HangingCtx:
    async def __aenter__(self):
        await asyncio.sleep(60)  # never completes within the test budget

    async def __aexit__(self, *exc):
        return False


def _assert_fast_false(coro_factory, budget: float) -> None:
    async def run() -> None:
        t0 = time.perf_counter()
        ok = await coro_factory()
        elapsed = time.perf_counter() - t0
        assert ok is False
        assert elapsed < budget + 1.0, f"health check took {elapsed:.2f}s (> {budget}s budget)"

    asyncio.run(run())


def test_postgres_health_check_times_out_fast() -> None:
    mgr = PostgresManager()
    mgr._health_timeout = 0.3

    class _Engine:
        def connect(self):  # noqa: ANN001 - test double
            return _HangingCtx()

    mgr._engine = _Engine()  # type: ignore[assignment]
    _assert_fast_false(mgr.health_check, 0.3)


def test_redis_health_check_times_out_fast() -> None:
    mgr = RedisManager()
    mgr._health_timeout = 0.3

    class _Client:
        async def ping(self):  # noqa: ANN001 - test double
            await asyncio.sleep(60)

    mgr._client = _Client()  # type: ignore[assignment]
    _assert_fast_false(mgr.health_check, 0.3)


def test_neo4j_health_check_times_out_fast() -> None:
    mgr = Neo4jManager()
    mgr._health_timeout = 0.3

    class _Driver:
        async def execute_query(self, *a, **k):  # noqa: ANN001 - test double
            await asyncio.sleep(60)

    mgr._driver = _Driver()  # type: ignore[assignment]
    _assert_fast_false(mgr.health_check, 0.3)


def test_health_check_returns_false_when_not_connected() -> None:
    # Disconnected managers report down immediately (no exception, no hang).
    for mgr in (PostgresManager(), RedisManager(), Neo4jManager()):
        assert asyncio.run(mgr.health_check()) is False
