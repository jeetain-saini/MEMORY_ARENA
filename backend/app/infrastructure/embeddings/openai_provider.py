"""OpenAIEmbeddingProvider — embeddings via the OpenAI API.

The OpenAI client is created lazily (and may be injected for testing), so this
module imports without the ``openai`` package installed and constructs without a
network call. ``health_check`` reports readiness from configuration (API key
present) rather than calling the API.
"""

from __future__ import annotations

from typing import Any

from app.application.interfaces.embedding_provider import EmbeddingProvider


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._client = client  # injectable AsyncOpenAI-like client

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _get_client(self) -> Any:
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("OPENAI_API_KEY is not configured")
            from openai import AsyncOpenAI  # lazy import

            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    async def embed_text(self, text: str) -> list[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = await self._get_client().embeddings.create(
            model=self._model, input=texts, dimensions=self._dimensions
        )
        return [item.embedding for item in response.data]

    async def health_check(self) -> bool:
        return bool(self._api_key) or self._client is not None
