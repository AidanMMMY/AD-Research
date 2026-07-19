"""News article embedding for RAG retrieval.

Generates vector embeddings for ``news_article`` rows and persists them in
``news_article.embedding`` (JSONB) along with the model name and timestamp.
The provider is pluggable; by default it uses the OpenAI-compatible
:class:`app.services.llm.embedding_provider.OpenAIEmbeddingProvider`.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.services.llm.embedding_provider import EmbeddingProvider
from app.services.news._model_loader import NewsArticle

logger = logging.getLogger(__name__)


class NewsEmbedder:
    """Generate and persist article embeddings for semantic search."""

    def __init__(
        self,
        db: Session,
        provider: EmbeddingProvider | None = None,
    ) -> None:
        self.db = db
        self.provider = provider or EmbeddingProvider()

    def _extract_text(self, article: NewsArticle) -> str:
        """Pick the richest available text and truncate to 2000 chars."""
        text = (
            article.full_content
            or article.body
            or article.summary
            or article.title
            or ""
        )
        return text[:2000]

    async def embed_article(self, article_id: int) -> list[float] | None:
        """Embed a single ``news_article`` row and write the result.

        Returns the embedding vector on success, or ``None`` when the row
        has no usable text, the provider is unavailable, or the call fails.
        """
        article = self.db.get(NewsArticle, article_id)
        if article is None:
            logger.warning("embed_article: article %s not found", article_id)
            return None

        text = self._extract_text(article)
        if not text.strip():
            logger.debug("embed_article: no text for article %s", article_id)
            return None

        try:
            vector = await asyncio.to_thread(self.provider.embed, text)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("embed_article: provider error for article %s: %s", article_id, exc)
            return None

        if vector is None:
            logger.debug("embed_article: no vector returned for article %s", article_id)
            return None

        try:
            article.embedding = vector
            article.embedding_model = self.provider.model_name
            article.embedded_at = datetime.utcnow()
            self.db.commit()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("embed_article: failed to persist article %s: %s", article_id, exc)
            self.db.rollback()
            return None

        return vector
