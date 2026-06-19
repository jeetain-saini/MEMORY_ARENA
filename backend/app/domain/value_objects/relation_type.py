"""RelationType — the semantics of an edge between two memories.

These types form the vocabulary of MemoryArena's memory graph. They are domain
concepts only; how they are persisted (Neo4j) or traversed (retrieval) is not
the domain's concern.
"""

from __future__ import annotations

from enum import Enum


class RelationType(str, Enum):
    """How one memory relates to another."""

    RELATED_TO = "related_to"       # Generic, undirected association.
    DEPENDS_ON = "depends_on"       # Source requires target to hold/make sense.
    DERIVED_FROM = "derived_from"   # Source was inferred/distilled from target.
    REINFORCES = "reinforces"       # Source strengthens belief in target.
    CONTRADICTS = "contradicts"     # Source conflicts with target (drives reconciliation).
