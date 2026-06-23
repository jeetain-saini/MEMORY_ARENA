"""bounded_gather — run async work with a hard concurrency ceiling (Stage 18.4).

``asyncio.gather`` runs *everything* at once, which would open one DB session and
one graph connection per tenant simultaneously — fine for three tenants, a
connection-pool stampede for three thousand. ``bounded_gather`` caps the number
of in-flight coroutines with a semaphore while still overlapping I/O up to that
limit, and returns results in input order (so callers can zip them back to their
inputs). ``limit=1`` degrades to ordered sequential execution, which is the safe
default for backends with a single shared connection.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


async def bounded_gather(
    factories: Sequence[Callable[[], Awaitable[T]]], *, limit: int
) -> list[T]:
    """Run each coroutine factory with at most ``limit`` in flight; preserve order.

    Factories (not bare coroutines) are taken so nothing starts before the
    semaphore admits it — a coroutine created eagerly would already be scheduled.
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")
    semaphore = asyncio.Semaphore(limit)

    async def _run(factory: Callable[[], Awaitable[T]]) -> T:
        async with semaphore:
            return await factory()

    return await asyncio.gather(*(_run(f) for f in factories))


def chunked(items: Sequence[T], size: int) -> list[Sequence[T]]:
    """Split ``items`` into consecutive chunks of at most ``size`` (size >= 1)."""
    if size < 1:
        raise ValueError("size must be >= 1")
    return [items[i : i + size] for i in range(0, len(items), size)]
