"""Application entrypoint and composition root.

`create_app()` is the factory that assembles the FastAPI application:
configuration, logging, middleware, exception handlers, routers, and the
startup/shutdown lifecycle that owns the datastore connections. Keeping all
wiring here (rather than scattered at import time) makes the boot sequence
explicit and the app re-creatable in tests.

Startup order: configure logging -> connect Postgres -> Redis -> Neo4j.
Shutdown unwinds in reverse so dependents close before their dependencies.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import RequestContextLogMiddleware, configure_logging
from app.infrastructure.cache.redis import redis_manager
from app.infrastructure.database.postgres import postgres_manager
from app.infrastructure.graph.neo4j import neo4j_manager

_logger = logging.getLogger("memoryarena.lifecycle")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage the application's startup and shutdown lifecycle."""
    settings: Settings = app.state.settings

    # --- Startup: bring datastore connections online (fail fast) ----------
    _logger.info("startup.begin", extra={"environment": settings.app_env})
    await postgres_manager.connect(settings)
    await redis_manager.connect(settings)
    await neo4j_manager.connect(settings)
    _logger.info("startup.complete")

    try:
        yield
    finally:
        # --- Shutdown: release resources in reverse dependency order ------
        _logger.info("shutdown.begin")
        await neo4j_manager.disconnect()
        await redis_manager.disconnect()
        await postgres_manager.disconnect()
        _logger.info("shutdown.complete")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    # Stash settings on app.state so the lifespan and overrides can reach them.
    app.state.settings = settings

    # Middleware (outermost first): CORS, then request-context logging.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextLogMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


# ASGI entrypoint: `uvicorn app.main:app`
app = create_app()
