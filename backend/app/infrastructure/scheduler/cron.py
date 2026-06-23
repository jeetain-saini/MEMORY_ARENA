"""Minimal 5-field cron matcher (no third-party dependency).

Supports the standard ``minute hour day-of-month month day-of-week`` syntax used
by the registered maintenance jobs: ``*``, fixed values, lists (``a,b``), ranges
(``a-b``), and steps (``*/n``, ``a-b/n``). Day-of-week is 0-6 with Sunday = 0
(``7`` also accepted as Sunday). Deliberately tiny — just enough to evaluate
whether a cron expression is due at a given minute, so the in-process scheduler
can honour the crons it already stores.

``cron_matches`` is pure and second-agnostic (it matches at minute resolution),
which is exactly what a once-per-minute scheduler tick needs.
"""

from __future__ import annotations

from datetime import datetime

_RANGES = {
    0: (0, 59),   # minute
    1: (0, 23),   # hour
    2: (1, 31),   # day of month
    3: (1, 12),   # month
    4: (0, 6),    # day of week (Sun=0)
}


def _part_matches(part: str, value: int, lo: int, hi: int) -> bool:
    step = 1
    if "/" in part:
        base, step_str = part.split("/", 1)
        step = int(step_str)
    else:
        base = part
    if base == "*":
        start, end = lo, hi
    elif "-" in base:
        start_str, end_str = base.split("-", 1)
        start, end = int(start_str), int(end_str)
    else:
        start = end = int(base)
    if value < start or value > end:
        return False
    return (value - start) % step == 0


def _field_matches(field: str, value: int, lo: int, hi: int) -> bool:
    return any(_part_matches(part, value, lo, hi) for part in field.split(","))


def cron_matches(expression: str, when: datetime) -> bool:
    """Return True if ``expression`` is due at ``when`` (minute resolution)."""
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError(f"expected 5 cron fields, got {len(fields)!r}: {expression!r}")

    dow = when.isoweekday() % 7  # Mon..Sun (1..7) -> Mon..Sat=1..6, Sun=0
    values = {0: when.minute, 1: when.hour, 2: when.day, 3: when.month, 4: dow}

    minute_h_month_ok = all(
        _field_matches(fields[i], values[i], *_RANGES[i]) for i in (0, 1, 3)
    )
    if not minute_h_month_ok:
        return False

    dom_field, dow_field = fields[2], fields[4]
    dom_ok = _field_matches(dom_field, values[2], *_RANGES[2])
    # Accept "7" as Sunday in addition to "0".
    dow_ok = _field_matches(dow_field, values[4], *_RANGES[4]) or (
        dow == 0 and _field_matches(dow_field, 7, 0, 7)
    )

    # Vixie-cron rule: when either day field is restricted, the match is an OR;
    # when both are "*", it is an AND (always true here).
    if dom_field == "*" or dow_field == "*":
        return dom_ok and dow_ok
    return dom_ok or dow_ok
