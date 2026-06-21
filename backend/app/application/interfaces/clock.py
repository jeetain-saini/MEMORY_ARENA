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
    """A time source with two faces.

    ``now()`` is **monotonic** (durations only); ``now_epoch()`` is **wall-clock**
    Unix time (absolute timestamps). They are intentionally separate: monotonic
    time is immune to clock adjustments and right for measuring stage latency,
    while Unix time is what JWT ``iat``/``exp`` and refresh-token expiry require.
    Both are injectable so tokens and timings stay deterministic in tests.
    """

    @abstractmethod
    def now(self) -> float:
        """Return the current monotonic time in seconds (for durations)."""

    @abstractmethod
    def now_epoch(self) -> float:
        """Return the current wall-clock time as Unix epoch seconds."""
