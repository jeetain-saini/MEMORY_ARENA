"""DeterministicEmbeddingProvider — dependency-free, reproducible embeddings.

Derives a stable pseudo-vector from a hash of the text. It is NOT semantically
meaningful, but it is fast, offline, and deterministic — ideal as the default in
development and for tests, so the whole embedding pipeline can be exercised
without API keys or model downloads.
"""

from __future__ import annotations

import hashlib

from app.application.interfaces.embedding_provider import EmbeddingProvider


class DeterministicEmbeddingProvider(EmbeddingProvider):
    def __init__(self, *, model_name: str = "deterministic-hash-v1", dimensions: int = 1536) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self._model_name = model_name
        self._dimensions = dimensions

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed_text(self, text: str) -> list[float]:
        return self._vector(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def _vector(self, text: str) -> list[float]:
        # Expand a digest into `dimensions` bytes, then scale each to [-1, 1].
        out: list[float] = []
        counter = 0
        while len(out) < self._dimensions:
            digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
            for byte in digest:
                if len(out) >= self._dimensions:
                    break
                out.append((byte / 127.5) - 1.0)
            counter += 1
        return out
