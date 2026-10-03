from __future__ import annotations

from pathlib import Path


class SentenceEmbedder:
    """Local CPU embeddings; no text is sent to an embedding provider."""

    def __init__(self, model_name: str, cache_dir: str):
        self.model_name = model_name
        self.cache_dir = cache_dir
        self._model = None

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding

            Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
            self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)
        return self._model

    def embed(self, text: str) -> list[float]:
        vectors = self._load().embed([text])
        return [float(value) for value in next(iter(vectors))]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [[float(value) for value in vector] for vector in self._load().embed(texts)]
