"""Aggregate router for API v1.

Collects every v1 route module under a single router that `main.py` mounts at
the configured `/api/v1` prefix. New resource routers are included here as the
API grows.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import health, memories

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(memories.router)
