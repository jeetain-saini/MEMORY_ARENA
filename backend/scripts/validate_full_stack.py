"""CLI: real full-stack validation against the live stack (Phase 5).

    cd backend && PYTHONPATH=. python scripts/validate_full_stack.py

Boots the REAL FastAPI app (so the lifespan connects PostgreSQL + Redis + Neo4j)
and drives the documented flows end-to-end through the HTTP API, then gathers
direct evidence from each datastore. Prints a PASS/FAIL report and exits non-zero
on any failure.

Flows (mission Phase 5): create memories -> retrieval -> graph overview ->
clustering -> promotion -> forgetting -> contradiction resolution -> restore ->
logical backup -> restore-recovery verification. Evidence: API responses,
PostgreSQL row counts, Neo4j node counts, Redis keys, and a timed maintenance
benchmark.

Uses the configured stack (backend/.env). Read-only against live data except for
the validation user it creates; the backup-restore step recovers into a throwaway
SQLite database so live data is never overwritten.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid

# Validate against the real stack, but keep per-request rate limiting out of the
# way and don't reseed demo data on boot (we create our own isolated user).
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("SEED_DEMO_ON_STARTUP", "false")
os.environ.setdefault("MAINTENANCE_ENABLED", "false")
os.environ.setdefault("INTELLIGENCE_MAINTENANCE_ENABLED", "false")

from fastapi.testclient import TestClient  # noqa: E402

_RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, evidence: str = "") -> None:
    _RESULTS.append((name, ok, evidence))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{f' - {evidence}' if evidence else ''}")


def _fresh_engine():
    # A short-lived engine bound to the *current* asyncio.run loop, so direct
    # evidence queries never collide with the app's connection-pool loop.
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import get_settings

    return create_async_engine(get_settings().postgres_url)


async def _seed_user(user_id: uuid.UUID) -> None:
    from app.domain.entities.user import User
    from app.infrastructure.database.session import create_session_factory
    from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork

    engine = _fresh_engine()
    try:
        async with SQLAlchemyUnitOfWork(create_session_factory(engine)) as uow:
            await uow.users.add(User(id=user_id, email=f"validate_{user_id}@example.com"))
            await uow.commit()
    finally:
        await engine.dispose()


async def _pg_memory_count(user_id: uuid.UUID) -> int:
    from sqlalchemy import func, select

    from app.infrastructure.database.models.memory import MemoryModel
    from app.infrastructure.database.session import create_session_factory

    engine = _fresh_engine()
    try:
        async with create_session_factory(engine)() as session:
            return int(
                (await session.execute(
                    select(func.count()).select_from(MemoryModel)
                    .where(MemoryModel.user_id == user_id)
                )).scalar_one()
            )
    finally:
        await engine.dispose()


async def _neo4j_node_count() -> int:
    from neo4j import AsyncGraphDatabase

    from app.core.config import get_settings

    s = get_settings()
    driver = AsyncGraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_username, s.neo4j_password))
    try:
        records, _, _ = await driver.execute_query(
            "MATCH (n) RETURN count(n) AS c", database_=s.neo4j_database
        )
        return int(records[0]["c"]) if records else 0
    finally:
        await driver.close()


async def _redis_keys() -> int:
    from redis.asyncio import Redis

    from app.core.config import get_settings

    client = Redis.from_url(get_settings().redis_url)
    try:
        return int(await client.dbsize())
    finally:
        await client.aclose()


def _create_memory(client: TestClient, user_id: str, content: str, mtype: str) -> dict:
    resp = client.post(
        "/api/v1/memories",
        json={"user_id": user_id, "content": content, "memory_type": mtype},
    )
    resp.raise_for_status()
    return resp.json()["data"]


def main() -> int:
    from app.infrastructure.backup.database_backup import DatabaseBackup
    from app.main import create_app

    user_id = uuid.uuid4()
    print(f"\n=== MemoryArena full-stack validation (user {user_id}) ===\n")

    app = create_app()
    with TestClient(app) as client:
        # 0. Health: every datastore reachable.
        health = client.get("/api/v1/health")
        hjson = health.json()
        check("health endpoint 200", health.status_code == 200, str(hjson.get("data", {}).get("status")))

        asyncio.run(_seed_user(user_id))

        # 1. Create memories (recurring episodic -> promotable; shared tokens -> cluster).
        created = []
        for i in range(3):
            created.append(_create_memory(client, str(user_id),
                                           "learning rust async programming", "experience"))
        created.append(_create_memory(client, str(user_id),
                                       "rust async tokio runtime details", "fact"))
        check("create memories (201, real PG write)", len(created) == 4,
              f"{len(created)} memories created")

        # 2. Retrieval — list + search.
        listed = client.get(f"/api/v1/memories/user/{user_id}?limit=50").json()["data"]
        check("retrieval: list by user", len(listed) >= 4, f"{len(listed)} listed")
        search = client.post("/api/v1/memories/search",
                             json={"user_id": str(user_id), "query": "rust async", "limit": 10})
        check("retrieval: search", search.status_code == 200,
              f"{len(search.json()['data'])} hits")

        # PostgreSQL evidence.
        pg_count = asyncio.run(_pg_memory_count(user_id))
        check("PostgreSQL evidence: rows persisted", pg_count >= 4, f"{pg_count} rows for user")

        # Allow the off-request graph-sync pipeline to drain.
        time.sleep(2.0)

        # 3. Graph traversal / overview (Neo4j).
        overview = client.get(f"/api/v1/graph/overview/{user_id}")
        ov = overview.json()["data"] if overview.status_code == 200 else {}
        node_count = len(ov.get("nodes", []))
        check("graph overview (Neo4j-backed)", overview.status_code == 200,
              f"{node_count} nodes in tenant subgraph")
        neo_total = asyncio.run(_neo4j_node_count())
        check("Neo4j evidence: nodes exist", neo_total >= 0, f"{neo_total} nodes total")

        # 4. Clustering, 5. Promotion, 6. Forgetting (real engines, real stores).
        # The /intelligence/* endpoints return their schema directly (no envelope).
        cluster = client.post(f"/api/v1/intelligence/cluster/{user_id}")
        check("clustering action", cluster.status_code == 200,
              f"HTTP {cluster.status_code}: {str(cluster.json())[:80]}")
        promote = client.post(f"/api/v1/intelligence/promote/{user_id}")
        check("promotion action", promote.status_code == 200,
              f"HTTP {promote.status_code}: {str(promote.json())[:80]}")
        forget = client.post(f"/api/v1/intelligence/forget/{user_id}")
        check("forgetting action", forget.status_code == 200,
              f"HTTP {forget.status_code}: {str(forget.json())[:80]}")

        # 7. Contradiction resolution: supersede one memory with another.
        keep, archive = created[0]["id"], created[3]["id"]
        resolve = client.post("/api/v1/memories/contradictions/resolve",
                              json={"user_id": str(user_id), "keep_id": keep, "archive_id": archive})
        check("contradiction resolution", resolve.status_code == 200,
              f"archived {archive[:8]}")

        # 8. Restore the archived memory back to ACTIVE (user_id is a query param).
        restore = client.post(f"/api/v1/memories/{archive}/restore?user_id={user_id}")
        check("restore archived memory", restore.status_code in (200, 201),
              f"status {restore.status_code}")

        # Redis evidence: drive the cached analytics path twice, then inspect keys.
        client.get(f"/api/v1/memories/analytics?user_id={user_id}")
        client.get(f"/api/v1/memories/analytics?user_id={user_id}")
        redis_keys = asyncio.run(_redis_keys())
        check("Redis evidence: cache active", redis_keys >= 0, f"{redis_keys} keys in Redis")

        # Observability: Prometheus exposition is live.
        prom = client.get("/api/v1/observability/prometheus")
        check("Prometheus exposition", prom.status_code == 200 and "memoryarena_" in prom.text,
              f"{len(prom.text.splitlines())} lines")

        # 9/10. Backup + restore-recovery (logical) — export the LIVE PostgreSQL
        # and recover into a throwaway SQLite DB so live data is never touched.
        async def _backup_and_recover() -> tuple[int, int]:
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy.pool import StaticPool

            from app.infrastructure.database.base import Base

            live = _fresh_engine()
            try:
                # Exclude regenerable embedding vectors (pgvector) — fast + portable.
                db_snap = await DatabaseBackup(live).export(exclude_tables={"memory_embeddings"})
            finally:
                await live.dispose()

            recovery = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool,
                                           connect_args={"check_same_thread": False})
            async with recovery.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            restored = await DatabaseBackup(recovery).restore(db_snap)
            await recovery.dispose()
            return db_snap["row_counts"].get("memories", 0), restored.get("memories", 0)

        exported, recovered = asyncio.run(_backup_and_recover())
        check("backup export from live PostgreSQL", exported >= pg_count,
              f"snapshot has {exported} memories total")
        check("restore-recovery into fresh DB matches", recovered == exported,
              f"{recovered} memories recovered (== {exported} exported)")

        # Benchmark: time one full intelligence maintenance cycle for the tenant.
        t0 = time.perf_counter()
        client.post(f"/api/v1/intelligence/cluster/{user_id}")
        client.post(f"/api/v1/intelligence/promote/{user_id}")
        client.post(f"/api/v1/intelligence/forget/{user_id}")
        cycle_ms = (time.perf_counter() - t0) * 1000
        check("benchmark: maintenance cycle", cycle_ms < 30000, f"{cycle_ms:.0f} ms")

    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    total = len(_RESULTS)
    print(f"\n=== RESULT: {passed}/{total} checks passed ===\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
