"""News article translation service.

Calls DeepSeek to translate the body (or Jina-fetched ``full_content``)
of an English :class:`NewsArticle` into Chinese, then caches the result
on the row so subsequent reads are free.

Design notes
------------
* **Source of truth**: we prefer ``full_content`` over ``body`` when both
  are present, because the Jina-fetched Markdown is the richer text the
  user will actually see on the detail page. Falling back to ``body``
  keeps the endpoint useful for crawlers that haven't filled
  ``full_content`` yet.
* **Language gate**: the public service refuses to translate anything
  that isn't ``language == "en"``. CN / HK / GLOBAL content stays
  untouched and we return ``None`` so the API can answer 400.
* **Caching**: the translation is written to ``translated_zh`` /
  ``translation_generated_at``. Re-running with the cache present is a
  no-op — we read straight from the row. The DB column doubles as the
  "did we already translate this" sentinel.
* **Rate-limit**: enforced at the API layer (per user / per day), not
  here, mirroring ``research_report_service.summarize_with_deepseek``.
* **Failure modes**: provider unavailable (no API key), LLM timeout,
  or 429 all return ``None`` so the API layer can return a 5xx-ish
  hint; the row stays untranslated for the next call.

Mirrors ``app.services.research_report_service.ResearchReportService``
style: ``chat()`` with retry, single-flight Redis lock lives in the API
layer.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.services.news._model_loader import NewsArticle

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_TRANSLATION_SYSTEM = (
    "你是一名严谨的中英双语金融翻译。请将用户提供的英文资讯正文翻译为中文。\n"
    "要求：\n"
    "1. 保持 Markdown 结构（标题、列表、引用、链接、代码块）原样。\n"
    "2. 保留所有英文专有名词（公司名、产品名、人名、英文术语首次出现时可附中文译名）。\n"
    "3. 保留所有数字、货币符号、百分比、股票代码、URL。\n"
    "4. 输出纯中文译文，不要附加任何解释、注释或代码块标记。\n"
    "5. 如果原文极短或为空，直接返回空字符串。"
)

# Soft cap: 12,000 chars ≈ 3-4k tokens of input. DeepSeek handles
# 16k easily; we leave headroom for system prompt + output. Long articles
# get truncated with an explicit "(以下省略)" marker so the user can
# see we cut something.
_MAX_INPUT_CHARS = 12_000

# Detect the DeepSeek "no API key configured" placeholder so callers
# can distinguish a real response from the missing-config no-op.
_NO_KEY_HINT = "AI 功能未配置"


def _truncate(text: str) -> str:
    """Cap a long article body to ``_MAX_INPUT_CHARS`` for the prompt."""
    if len(text) <= _MAX_INPUT_CHARS:
        return text
    return text[: _MAX_INPUT_CHARS - 30].rstrip() + "\n\n（…以下省略…）"


def _pick_source(article: NewsArticle) -> str | None:
    """Pick the best source text for translation.

    Prefers the Jina-fetched ``full_content`` (Markdown, richer) over
    ``body`` (usually an excerpt). Returns ``None`` if neither is set.
    """
    if article.full_content and article.full_content.strip():
        return article.full_content
    if article.body and article.body.strip():
        return article.body
    return None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class NewsTranslationService:
    """Translate English news articles to Chinese using DeepSeek.

    Holds a DB session and writes the result back to the
    ``NewsArticle`` row. Stateless apart from ``self.db``; safe to
    instantiate per request.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- Public API -----------------------------------------------------

    def get_cached_translation(self, article_id: int) -> str | None:
        """Return the cached Chinese translation, or ``None`` if absent.

        Lightweight read — does **not** trigger the LLM. Useful for the
        API layer's "did we already translate this?" check before it
        spends rate-limit budget on another call.
        """
        article = self.db.get(NewsArticle, article_id)
        if article is None:
            return None
        return article.translated_zh

    def translate(self, article_id: int, *, target_language: str = "zh") -> dict[str, Any]:
        """Translate one article; persist the result on the row.

        Returns
        -------
        dict
            ``{translation: str, cached: bool, tokens_used: int | None,
            generated_at: iso | None, source_language: str,
            target_language: str}``.

        Raises
        ------
        ValueError
            - Article not found.
            - Article is not in English (``language != "en"``).
            - Article has no body / full_content to translate.
        RuntimeError
            - DeepSeek call failed (timeout, 429, no key configured).
        """
        if target_language and target_language != "zh":
            # v1 only ships zh; reject anything else loudly so future
            # maintainers see where to extend.
            raise ValueError(
                f"Unsupported target_language: {target_language!r} (only 'zh' is supported)"
            )

        article = self.db.get(NewsArticle, article_id)
        if article is None:
            raise ValueError(f"NewsArticle {article_id} not found")

        if (article.language or "").lower() != "en":
            raise ValueError(
                f"Article {article_id} language is {article.language!r}; "
                "translation is only enabled for English content"
            )

        if article.translated_zh:
            # Cache hit — return immediately, do NOT burn LLM tokens.
            return {
                "translation": article.translated_zh,
                "cached": True,
                "tokens_used": None,
                "generated_at": (
                    article.translation_generated_at.isoformat()
                    if article.translation_generated_at
                    else None
                ),
                "source_language": article.language or "en",
                "target_language": target_language,
            }

        source = _pick_source(article)
        if not source:
            raise ValueError(
                f"Article {article_id} has no body / full_content to translate"
            )

        # Call DeepSeek (imported lazily so unit tests can patch the
        # provider without paying the OpenAI SDK import cost).
        from app.services.llm import get_llm_provider

        provider = get_llm_provider()
        if not provider.is_available:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured on the server")

        system = _TRANSLATION_SYSTEM
        user = _truncate(source)

        content, tokens = self._call_llm_with_retry(provider, system, user)
        if not content:
            raise RuntimeError(
                "DeepSeek returned no usable translation (timeout, 429 or empty response)"
            )

        # Persist. We use a fresh ``now`` rather than func.now() so the
        # returned ``generated_at`` matches what was actually written.
        now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        article.translated_zh = content
        article.translation_generated_at = now
        self.db.commit()

        return {
            "translation": content,
            "cached": False,
            "tokens_used": tokens,
            "generated_at": now.isoformat(),
            "source_language": article.language or "en",
            "target_language": target_language,
        }

    # ---- LLM helpers ----------------------------------------------------

    def _call_llm_with_retry(
        self, provider, system: str, user: str
    ) -> tuple[str | None, int | None]:
        """Single DeepSeek call with one 429 retry.

        Returns ``(content, tokens_used)``. ``tokens_used`` is reported
        as ``None`` when DeepSeek isn't configured or the call fails —
        the provider does not currently expose a usage field on its
        ``chat()`` shortcut, so we report ``None`` rather than guess.
        """
        for attempt in range(2):
            try:
                start = time.monotonic()
                content = provider.chat(
                    messages=[{"role": "user", "content": user}],
                    system=system,
                )
                elapsed = time.monotonic() - start
                if elapsed > 30.0:
                    logger.warning(
                        "News translation LLM call took %.2fs (>30s); skipping",
                        elapsed,
                    )
                    return None, None
                if not content:
                    return None, None
                # Strip the no-key placeholder — it's not a real
                # translation and we should already have raised above
                # if the key is missing, but be defensive.
                if _NO_KEY_HINT in content:
                    logger.info(
                        "News translation LLM: no API key configured, skipping"
                    )
                    return None, None
                return content.strip(), None
            except Exception as exc:
                msg = str(exc).lower()
                is_429 = "429" in msg or "rate" in msg
                if is_429 and attempt == 0:
                    logger.warning(
                        "News translation LLM 429; retrying in 2s (article call)"
                    )
                    time.sleep(2.0)
                    continue
                logger.warning("News translation LLM call failed: %s", exc)
                return None, None
        return None, None