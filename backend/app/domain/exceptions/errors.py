"""Domain exceptions.

Pure Python errors raised by the domain when an invariant is violated. They are
framework-agnostic — the API layer is responsible for mapping them to HTTP
responses (see app/core/exceptions.py). The domain never imports HTTP concepts.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain-rule violations."""


class MemoryValidationError(DomainError):
    """A memory's data violates a domain invariant (e.g. empty content)."""


class InvalidMemoryStateError(DomainError):
    """An operation was attempted that is illegal in the memory's current state."""


class InvalidRelationError(DomainError):
    """A memory relation violates an invariant (e.g. a self-referential edge)."""


class InvalidScoreError(DomainError):
    """A score component is outside the permitted [0.0, 1.0] range."""
