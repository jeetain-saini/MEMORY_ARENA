"""Clock port — an injectable source of monotonic time.

Observability needs to measure how long pipeline stages take, but the
application layer must stay deterministic and testable: reading the wall clock
directly would make timings non-reproducible and couple the core to the system.
So time is a *port*. A real ``MonotonicClock`` (infrastructure) reads
``time.monotonic`` in production; a ``FrozenClock`` (application/services) gives
deterministic, reproducible durations in tests.

``now()`` returns a monotonically non-decreasing value in **seconds**; only
*differences* are meaningful (it is not wall-clock time and not for timestamps).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Clock(ABC):
    """A monotonic time source. Differences between ``now()`` reads are durations."""

    @abstractmethod
    def now(self) -> float:
        """Return the current monotonic time in seconds."""
