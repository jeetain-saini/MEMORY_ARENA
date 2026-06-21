"""Unit tests for the Clock port implementations (Stage 13).

FrozenClock is deterministic (the basis for reproducible stage timing);
MonotonicClock is the real adapter and only needs to be non-decreasing.
"""

from __future__ import annotations

from app.application.services.observability.frozen_clock import FrozenClock
from app.infrastructure.observability.monotonic_clock import MonotonicClock


def test_frozen_clock_is_static_by_default() -> None:
    clock = FrozenClock()
    assert clock.now() == 0.0
    assert clock.now() == 0.0  # no auto-advance


def test_frozen_clock_manual_advance() -> None:
    clock = FrozenClock(start=10.0)
    assert clock.now() == 10.0
    clock.advance(2.5)
    assert clock.now() == 12.5


def test_frozen_clock_auto_advance_yields_fixed_deltas() -> None:
    clock = FrozenClock(auto_advance=0.5)
    # Each read returns the current value, then advances by the step.
    assert clock.now() == 0.0
    assert clock.now() == 0.5
    assert clock.now() == 1.0


def test_frozen_clock_auto_advance_measures_constant_duration() -> None:
    # A stage that reads once at start and once at end measures exactly one step,
    # regardless of intervening reads-free work. This is what makes durations
    # deterministic in the agent trace tests.
    clock = FrozenClock(auto_advance=0.01)
    start = clock.now()
    end = clock.now()
    assert round((end - start) * 1000, 3) == 10.0


def test_monotonic_clock_is_non_decreasing() -> None:
    clock = MonotonicClock()
    a = clock.now()
    b = clock.now()
    assert b >= a


# --- now_epoch (Stage 14: wall-clock for token expiry) ---------------------

def test_monotonic_clock_now_epoch_is_wall_time() -> None:
    import time

    clock = MonotonicClock()
    assert abs(clock.now_epoch() - time.time()) < 5.0


def test_frozen_clock_epoch_is_controllable() -> None:
    clock = FrozenClock(epoch=1_700_000_000.0)
    assert clock.now_epoch() == 1_700_000_000.0
    # now_epoch does not auto-advance (unlike monotonic now()).
    assert clock.now_epoch() == 1_700_000_000.0


def test_frozen_clock_advance_moves_both_clocks() -> None:
    clock = FrozenClock(start=10.0, epoch=1000.0)
    clock.advance(5.0)
    assert clock.now() == 15.0
    assert clock.now_epoch() == 1005.0
