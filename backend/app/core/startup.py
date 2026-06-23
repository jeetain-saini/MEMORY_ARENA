"""Startup resilience helpers (production hardening).

``await_healthy`` eagerly verifies a datastore is reachable at startup, retrying
a health probe with capped exponential backoff. This matters because SQLAlchemy
(and the other managers) connect *lazily* — ``connect()`` only builds the engine,
so a dead database is not noticed until the first query deep inside a request (or,
worse, inside startup seeding, crashing the whole app with an opaque trace). By
probing here we either confirm readiness or fail fast with a clear, structured
diagnostic that names the datastore and the underlying error.

Required datastores (Postgres) raise :class:`DatastoreUnavailableError` when they
never come up; optional ones (Redis/Neo4j when degraded operation is acceptable)
log and return ``False`` so a minimal deploy still boots.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

_logger = logging.getLogger("memoryarena.startup")


class DatastoreUnavailableError(RuntimeError):
    """A required datastore did not become healthy within the retry budget."""


async def await_healthy(
    name: str,
    health_check: Callable[[], Awaitable[bool]],
    *,
    attempts: int = 10,
    base_delay: float = 0.5,
    max_delay: float = 10.0,
    required: bool = True,
) -> bool:
    """Retry ``health_check`` with exponential backoff until it passes.

    Returns True once healthy. If it never passes within ``attempts``: raises
    :class:`DatastoreUnavailableError` when ``required`` (fail fast at startup),
    else logs and returns False (degraded but booting).
    """
    last_error = "health check returned False"
    for attempt in range(1, attempts + 1):
        try:
            if await health_check():
                _logger.info(
                    "startup.datastore_ready", extra={"datastore": name, "attempt": attempt}
                )
                return True
        except Exception as exc:  # noqa: BLE001 — probe must classify, not propagate
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < attempts:
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            _logger.warning(
                "startup.datastore_retry",
                extra={
                    "datastore": name,
                    "attempt": attempt,
                    "max_attempts": attempts,
                    "delay_s": round(delay, 2),
                    "error": last_error,
                },
            )
            await asyncio.sleep(delay)
    if required:
        raise DatastoreUnavailableError(
            f"{name} unavailable after {attempts} attempts ({last_error})"
        )
    _logger.error(
        "startup.datastore_degraded",
        extra={"datastore": name, "attempts": attempts, "error": last_error},
    )
    return False
