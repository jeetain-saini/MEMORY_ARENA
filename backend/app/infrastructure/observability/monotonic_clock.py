"""MonotonicClock — the production Clock adapter.

Reads ``time.monotonic``, which is immune to wall-clock adjustments (NTP, DST)
and therefore the correct source for measuring durations. Stateless, so it is
safe to share process-wide and to copy through agent state.
"""

from __future__ import annotations

import time

from app.application.interfaces.clock import Clock


class MonotonicClock(Clock):
    def now(self) -> float:
        return time.monotonic()

    def now_epoch(self) -> float:
        return time.time()
