"""PasswordHasher port — one-way password hashing/verification.

The application depends on this abstraction; the bcrypt adapter lives in
infrastructure. Keeping it a port means the hashing scheme can change (argon2,
peppering) without touching the auth service.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class PasswordHasher(ABC):
    @abstractmethod
    def hash(self, password: str) -> str:
        """Return a salted one-way hash of ``password``."""

    @abstractmethod
    def verify(self, password: str, password_hash: str) -> bool:
        """Return True iff ``password`` matches ``password_hash`` (constant-time)."""
