"""Small text helpers shared by context-assembly services."""

from __future__ import annotations


def jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity of two token sets; 0.0 if both empty."""
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace to single spaces and trim."""
    return " ".join(text.split())
