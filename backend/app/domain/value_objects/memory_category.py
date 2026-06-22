"""MemoryCategory — episodic vs semantic memory (Stage 17).

Episodic memories are time-bound events/experiences; semantic memories are
durable knowledge about the user (facts, skills, preferences, goals, projects).
Each ``MemoryType`` has a default category, but a memory may carry an explicit
override (e.g. after episodic->semantic promotion).
"""

from __future__ import annotations

from enum import Enum

from app.domain.value_objects.memory_type import MemoryType


class MemoryCategory(str, Enum):
    EPISODIC = "episodic"   # events, conversations, one-time experiences
    SEMANTIC = "semantic"   # skills, preferences, facts, long-term identity


#: Default type -> category mapping. Only EXPERIENCE is episodic by default.
DEFAULT_CATEGORY: dict[MemoryType, MemoryCategory] = {
    MemoryType.EXPERIENCE: MemoryCategory.EPISODIC,
    MemoryType.FACT: MemoryCategory.SEMANTIC,
    MemoryType.SKILL: MemoryCategory.SEMANTIC,
    MemoryType.GOAL: MemoryCategory.SEMANTIC,
    MemoryType.PROJECT: MemoryCategory.SEMANTIC,
    MemoryType.PREFERENCE: MemoryCategory.SEMANTIC,
}


def default_category(memory_type: MemoryType) -> MemoryCategory:
    return DEFAULT_CATEGORY.get(memory_type, MemoryCategory.SEMANTIC)
