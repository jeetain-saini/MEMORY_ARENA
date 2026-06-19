"""MemoryType — the category of knowledge a memory represents.

A pure-Python enum. The taxonomy is deliberately small and stable; it shapes how
memories are scored, retrieved, and promoted downstream without the domain
knowing anything about those mechanisms.
"""

from __future__ import annotations

from enum import Enum


class MemoryType(str, Enum):
    """What kind of thing the memory captures."""

    FACT = "fact"               # An objective statement: "User's timezone is IST".
    GOAL = "goal"               # A desired outcome: "Ship MemoryArena v1 by Q3".
    PREFERENCE = "preference"   # A stable like/dislike: "Prefers concise answers".
    SKILL = "skill"             # A learned capability: "Can write Cypher queries".
    PROJECT = "project"         # A bounded effort with context: "MemoryArena".
    EXPERIENCE = "experience"   # A time-stamped episode: "Demo failed on 2026-06-01".
