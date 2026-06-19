"""LocalBGEEmbeddingProvider — embeddings from a local BGE model.

Runs a sentence-transformers BGE model on-box (no API, no per-call cost). The
model is loaded lazily (and may be injected for testing), so importing this
module does not require ``sentence-transformers`` to be installed.

Note: BGE models have their own native dimensionality (e.g. 384/768/1024) which
differs from OpenAI's 1536. Switching to BGE in production is therefore a
model-migration event (re-embed into a matching-dimension column) — see the
migration strategy in docs/architecture.md.
"""

from __future__ import annotations

from typing import Any

from app.application.interfaces.embedding_provider import EmbeddingProvider


class LocalBGEEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        *,
        model_name: str = "BAAI/bge-small-en-v1.5",
        dimensions: int = 384,
        model: Any | None = None,
    ) -> None:
        self._model_name = model_name
        self._dimensions = dimensions
        self._model = model  # injectable SentenceTransformer-like model

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _get_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # lazy import

            self._model = SentenceTransformer(self._model_name)
        return self._model

    async def embed_text(self, text: str) -> list[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors = self._get_model().encode(texts, normalize_embeddings=True)
        return [list(map(float, v)) for v in vectors]

    async def health_check(self) -> bool:
        try:
            self._get_model()
            return True
        except Exception:  # noqa: BLE001 - missing model/library => not ready
            return False
