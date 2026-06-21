"""FrozenClock — a deterministic Clock for tests and reproducible runs.

Time only moves when you tell it to. Two modes, composable:

* ``advance(seconds)`` — explicit manual control.
* ``auto_advance`` — every ``now()`` read advances the clock by a fixed step
  *after* returning the current value. This yields deterministic, monotonic,
  non-zero stage durations without depending on real wall-clock timing: a stage
  that reads the clock once at start and once at end measures exactly one
  ``auto_advance`` step, regardless of what happened in between.

It is a legitimate (pure, side-effect-free) ``Clock`` implementation, not a
mock — so it can drive deterministic timing in any offline context.
"""

from __future__ import annotations

from app.application.interfaces.clock import Clock


class FrozenClock(Clock):
    def __init__(
        self, *, start: float = 0.0, auto_advance: float = 0.0, epoch: float = 0.0
    ) -> None:
        self._t = float(start)
        self._auto_advance = float(auto_advance)
        # Wall-clock value, controlled independently of the monotonic ``now()``
        # so token-expiry tests can advance time deterministically.
        self._epoch = float(epoch)

    def now(self) -> float:
        current = self._t
        self._t += self._auto_advance
        return current

    def now_epoch(self) -> float:
        return self._epoch

    def advance(self, seconds: float) -> None:
        """Move both the monotonic and wall clocks forward by ``seconds``."""
        self._t += float(seconds)
        self._epoch += float(seconds)
