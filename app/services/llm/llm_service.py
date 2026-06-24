"""LLM high-level service with caching and rate limiting.

Wraps LLMProvider with Redis caching to avoid re-processing
identical prompts, and provides template-based prompt building
for common research patterns.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone

from app.core.cache import cache_get, cache_set
from app.core.exceptions import DataProviderError
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# Cache TTL for LLM responses: 1 hour for volatile data (prices),
# 24 hours for static data (company profiles)
CACHE_TTL_VOLATILE = 3600
CACHE_TTL_STATIC = 86400


class LLMService:
    """High-level LLM service with caching and prompt templates."""

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def _cache_key(self, prefix: str, *args: str) -> str:
        """Generate a deterministic cache key."""
        content = "|".join(args)
        digest = hashlib.sha256(content.encode()).hexdigest()[:16]
        return f"llm:{prefix}:{digest}"

    def complete_with_cache(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        ttl: int = CACHE_TTL_VOLATILE,
    ) -> str:
        """Complete with Redis caching layer."""
        key = self._cache_key("complete", prompt, system or "", str(max_tokens))
        cached = cache_get(key)
        if cached is not None:
            logger.debug("LLM cache hit for key=%s", key)
            return cached

        try:
            result = self.provider.complete(
                prompt=prompt,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            logger.error("LLM completion failed: %s", exc)
            raise DataProviderError(f"LLM completion failed: {exc}") from exc

        cache_set(key, result, ttl=ttl)
        return result

    def chat_with_cache(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        ttl: int = CACHE_TTL_VOLATILE,
    ) -> str:
        """Chat with Redis caching (caches on last user message)."""
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            "",
        )
        key = self._cache_key("chat", last_user, system or "", str(max_tokens))
        cached = cache_get(key)
        if cached is not None:
            return cached

        try:
            result = self.provider.chat(
                messages=messages,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            logger.error("LLM chat failed: %s", exc)
            raise DataProviderError(f"LLM chat failed: {exc}") from exc

        cache_set(key, result, ttl=ttl)
        return result

    # ------------------------------------------------------------------
    # Prompt Templates
    # ------------------------------------------------------------------

    RESEARCH_ANALYST_SYSTEM = (
        "You are a professional equity research analyst. "
        "Write in clear, concise Chinese (Simplified) with professional tone. "
        "Use data to support your analysis. Be specific about numbers, trends, "
        "and signals. Flag both bullish and bearish factors. "
        "End with a one-sentence investment insight."
    )

    SENTIMENT_SYSTEM = (
        "You are a financial news sentiment classifier. "
        "Classify the sentiment of the given news article as: "
        "positive (bullish for the stock), negative (bearish), or neutral. "
        "Respond with ONLY a JSON object: "
        '{"label": "positive|negative|neutral", "score": -1.0_to_1.0, "confidence": 0.0_to_1.0}'
    )

    EARNINGS_SYSTEM = (
        "You are an equity research analyst specializing in earnings call analysis. "
        "Extract key insights from earnings call transcripts. "
        "Respond in Chinese (Simplified) with markdown formatting."
    )

    CHAT_SYSTEM = (
        "你是投资研究助手，可以访问平台的ETF筛选、技术指标和评分数据。"
        "回答需简洁、数据驱动，使用中文。"
        "当讨论具体标的时，优先引用提供的实时数据。"
        "如果数据不足以做出判断，明确说明。"
    )
