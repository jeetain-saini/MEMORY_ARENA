"""Health and version routes.

`/health` probes every backing datastore concurrently and reports an aggregate
status — the endpoint load balancers and orchestrators poll for readiness.
`/version` exposes build/runtime metadata for diagnostics.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Response, status

from app.api.v1.dependencies.providers import get_app_settings
from app.infrastructure.cache.redis import redis_manager
from app.infrastructure.database.postgres import postgres_manager
from app.infrastructure.graph.neo4j import neo4j_manager

router = APIRouter(tags=["system"])

_UP = "up"
_DOWN = "down"


@router.get("/health", summary="Aggregate health of the service and its datastores")
async def health(response: Response) -> dict[str, str]:
    """Probe Postgres, Redis, and Neo4j concurrently.

    Returns HTTP 200 when all dependencies are reachable, HTTP 503 otherwise, so
    orchestrators can gate traffic on readiness.
    """
    postgres_ok, redis_ok, neo4j_ok = await asyncio.gather(
        postgres_manager.health_check(),
        redis_manager.health_check(),
        neo4j_manager.health_check(),
    )

    all_up = postgres_ok and redis_ok and neo4j_ok
    if not all_up:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "healthy" if all_up else "degraded",
        "postgres": _UP if postgres_ok else _DOWN,
        "redis": _UP if redis_ok else _DOWN,
        "neo4j": _UP if neo4j_ok else _DOWN,
    }


@router.get("/version", summary="Service version and runtime metadata")
async def version() -> dict[str, str]:
    settings = get_app_settings()
    return {
        "name": settings.app_name,
        "version": settings.version,
        "environment": settings.app_env,
    }
