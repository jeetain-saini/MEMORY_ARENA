"""BcryptPasswordHasher — the production PasswordHasher adapter.

Uses bcrypt with a per-password random salt. bcrypt ignores input beyond 72
bytes, so the password is encoded and truncated defensively before hashing and
verifying (so a >72-byte password verifies consistently).
"""

from __future__ import annotations

import bcrypt

from app.application.interfaces.password_hasher import PasswordHasher

_MAX_BCRYPT_BYTES = 72


class BcryptPasswordHasher(PasswordHasher):
    def __init__(self, *, rounds: int = 12) -> None:
        self._rounds = rounds

    @staticmethod
    def _encode(password: str) -> bytes:
        return password.encode("utf-8")[:_MAX_BCRYPT_BYTES]

    def hash(self, password: str) -> str:
        salt = bcrypt.gensalt(rounds=self._rounds)
        return bcrypt.hashpw(self._encode(password), salt).decode("utf-8")

    def verify(self, password: str, password_hash: str) -> bool:
        if not password_hash:
            return False
        try:
            return bcrypt.checkpw(self._encode(password), password_hash.encode("utf-8"))
        except (ValueError, TypeError):
            # Malformed stored hash -> treat as a non-match rather than erroring.
            return False
