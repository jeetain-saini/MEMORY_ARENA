"""Aggregate router for API v1.

Collects every v1 route module under a single router that `main.py` mounts at
the configured `/api/v1` prefix. New resource routers are included here as the
API grows.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.dependencies.ratelimit import enforce_rate_limit
from app.api.v1.routes import (
    auth,
    context,
    graph,
    health,
    ingest,
    memories,
    observability,
    query,
    retrieval,
    summaries,
)

# The rate-limit dependency is attached at the aggregate router so every v1
# route is covered uniformly; it no-ops when disabled and exempts health/version.
api_router = APIRouter(dependencies=[Depends(enforce_rate_limit)])
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(memories.router)
api_router.include_router(retrieval.router)
api_router.include_router(context.router)
api_router.include_router(graph.router)
api_router.include_router(ingest.router)
api_router.include_router(query.router)
api_router.include_router(summaries.router)
api_router.include_router(observability.router)
