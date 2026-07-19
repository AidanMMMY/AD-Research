"""Embedding provider with OpenAI-compatible and local fallbacks.

A thin wrapper around the ``openai`` SDK for generating text embeddings.
It is intentionally provider-agnostic: set ``EMBEDDING_BASE_URL`` to any
OpenAI-compatible endpoint (SiliconFlow, OpenRouter, a local vLLM/Ollama
server, etc.) and ``EMBEDDING_MODEL`` to the model you want to use.

When no API key is configured, the provider falls back to a local
``sentence-transformers`` model.  If the local model is not installed or
fails to load, the provider is dormant and returns ``None`` instead of
raising.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)

# Strong Chinese embedding model available on most OpenAI-compatible Chinese
# inference platforms.  Override via env.
_DEFAULT_OPENAI_MODEL = "BAAI/bge-large-zh-v1.5"

# Small multilingual model used when no API key is available.  It runs on
# CPU, supports Chinese, and downloads automatically on first use.
_DEFAULT_LOCAL_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class OpenAIEmbeddingProvider:
    """Embedding provider via an OpenAI-compatible ``/embeddings`` endpoint."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("EMBEDDING_API_KEY") or ""
        self.base_url = base_url or os.getenv("EMBEDDING_BASE_URL")
        self.model = model or os.getenv("EMBEDDING_MODEL") or _DEFAULT_OPENAI_MODEL

        self._client: OpenAI | None = None
        if self.api_key:
            try:
                client_kwargs: dict[str, Any] = {"api_key": self.api_key}
                if self.base_url:
                    client_kwargs["base_url"] = self.base_url
                self._client = OpenAI(**client_kwargs)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Embedding client init failed: %s", exc)

    @property
    def is_available(self) -> bool:
        return self._client is not None

    def embed(self, text: str) -> list[float] | None:
        """Return an embedding vector for ``text`` or ``None`` on failure."""
        if not self.is_available:
            return None
        if not text or not text.strip():
            return None
        try:
            response = self._client.embeddings.create(
                input=text.strip(),
                model=self.model,
            )
            embedding = response.data[0].embedding
            return [float(x) for x in embedding]
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning("Embedding call failed (%s): %s", self.model, exc)
            return None


class LocalEmbeddingProvider:
    """CPU embedding provider using ``sentence-transformers``.

    This is a best-effort fallback when no OpenAI-compatible API key is
    configured.  The model is loaded lazily so import-time failures are
    avoided.
    """

    def __init__(self, model: str | None = None) -> None:
        self.model_name = model or os.getenv("LOCAL_EMBEDDING_MODEL") or _DEFAULT_LOCAL_MODEL
        self._model: Any | None = None

    @property
    def is_available(self) -> bool:
        if self._model is not None:
            return True
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            logger.info("Loaded local embedding model: %s", self.model_name)
            return True
        except Exception as exc:
            logger.warning(
                "Local embedding model %s not available: %s",
                self.model_name,
                exc,
            )
            self._model = False
            return False

    def embed(self, text: str) -> list[float] | None:
        if not self.is_available:
            return None
        if not text or not text.strip():
            return None
        try:
            return self._model.encode(text.strip(), convert_to_numpy=True).tolist()
        except Exception as exc:
            logger.warning("Local embedding failed: %s", exc)
            return None


class EmbeddingProvider:
    """Unified embedding provider: API first, then local fallback."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        local_model: str | None = None,
    ) -> None:
        self.api = OpenAIEmbeddingProvider(api_key=api_key, base_url=base_url, model=model)
        self.local = LocalEmbeddingProvider(model=local_model)

    @property
    def is_available(self) -> bool:
        return self.api.is_available or self.local.is_available

    @property
    def model_name(self) -> str:
        if self.api.is_available:
            return self.api.model
        return self.local.model_name

    def embed(self, text: str) -> list[float] | None:
        if self.api.is_available:
            return self.api.embed(text)
        return self.local.embed(text)
