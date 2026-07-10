"""Fetch full article body via Jina Reader (``r.jina.ai``).

Jina Reader is a free, no-auth-required service that takes any URL and
returns Markdown. We use it on-demand when a user clicks the
"load-full-text" button on the news detail page — never automatically,
because the service enforces a public rate limit and we don't want to
burn cycles on articles nobody ever opens.

Flow
----
1. Check ``news_article.full_content`` + ``full_content_fetched_at``.
   If the cache is fresh (< 24h) return it as-is.
2. Otherwise call ``https://r.jina.ai/{article.url}`` with a 15 s
   timeout. On success, store the (truncated) body back to the DB
   and return it.
3. On any HTTP error / timeout / unexpected exception, log it and
   return ``None`` — the caller then falls back to the original
   ``body`` (the RSS summary already available).

The 24-hour TTL is enforced by the caller; the fetcher itself just
re-fetches whenever invoked. That keeps the service unit-testable and
avoid time-of-day decisions inside the module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Final, Optional

import httpx
from sqlalchemy.orm import Session

from app.services.news._model_loader import NewsArticle

logger = logging.getLogger(__name__)

# Public Jina Reader endpoint. Free for personal use, no API key.
JINA_READER_URL: Final[str] = "https://r.jina.ai"

# 30-second timeout per request — Jina can be slow on large pages.
REQUEST_TIMEOUT: Final[float] = 30.0

# Hard cap on stored content to keep the DB row reasonable.
MAX_CONTENT_CHARS: Final[int] = 10_000

# Cache TTL applied by callers when deciding whether to re-fetch.
CACHE_TTL: Final[timedelta] = timedelta(hours=24)


@dataclass
class FetchResult:
    """Outcome of a :meth:`ContentFetcher.fetch` call."""

    success: bool
    content: str | None
    cached: bool
    error: str | None = None
    # AI-cleanup observability (M22-3, 2026-07-05). One of
    # ``"cleaned" | "skipped" | "failed" | "not_attempted" | None``.
    # ``None`` here means the fetcher did not actually call the AI
    # step (e.g. cache hit or Jina failed) — the row's
    # ``ai_cleanup_status`` keeps whatever value it already had so we
    # do not stomp a historical success.
    ai_cleanup_status: str | None = None


class ContentFetcher:
    """Lazy on-demand article-body fetcher.

    The class is intentionally cheap to instantiate — it carries no
    state beyond a reference to the SQLAlchemy session. Construct one
    per request and discard.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def fetch(self, article_id: int, *, force: bool = False) -> FetchResult:
        """Return full body for ``article_id``.

        Parameters
        ----------
        article_id:
            Primary key of the ``news_article`` row.
        force:
            If ``True``, ignore the cache TTL and re-fetch every time.
            Useful for tests.

        Returns
        -------
        :class:`FetchResult` — ``success=False`` means the upstream
        call failed and the caller should fall back to ``article.body``.
        """
        article = self.db.get(NewsArticle, article_id)
        if article is None:
            return FetchResult(success=False, content=None, cached=False,
                               error="article not found")
        if not article.url:
            return FetchResult(success=False, content=None, cached=False,
                               error="article has no url")

        # 1) Cache hit: still fresh and not empty.
        if not force and self._is_cache_fresh(article):
            return FetchResult(
                success=True,
                content=article.full_content,
                cached=True,
                ai_cleanup_status=article.ai_cleanup_status,
            )

        # 2) Fetch from Jina Reader.
        try:
            md = self._call_jina(article.url)
        except _JinaError as exc:
            logger.warning(
                "ContentFetcher: jina failed for article %s url=%s: %s",
                article_id, article.url, exc,
            )
            return FetchResult(success=False, content=None, cached=False,
                               error=str(exc))

        if not md:
            return FetchResult(success=False, content=None, cached=False,
                               error="empty response from Jina Reader")

        # 3) Use AI to clean up the content (remove ads, navigation, etc.)
        #    We no longer swallow the outcome — both the cleaned body and
        #    the structured status (cleaned / skipped / failed) come back
        #    so the row + the caller can surface "AI did nothing".
        content, ai_status = self._clean_with_ai(md.strip())

        # 4) Safety truncate.
        content = content.strip()
        truncated = False
        if len(content) > MAX_CONTENT_CHARS:
            content = content[:MAX_CONTENT_CHARS]
            truncated = True
            logger.info(
                "ContentFetcher: truncated article %s to %d chars",
                article_id, MAX_CONTENT_CHARS,
            )

        # 5) Store back to DB, including the AI-cleanup status.
        article.full_content = content
        article.full_content_fetched_at = datetime.now(tz=timezone.utc)
        article.ai_cleaned_at = datetime.now(tz=timezone.utc)
        article.ai_cleanup_status = ai_status
        try:
            self.db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ContentFetcher: db commit failed for article %s: %s",
                article_id, exc,
            )
            self.db.rollback()
            # Still return the content — caller got their answer.

        if truncated:
            content = content + "\n\n*[内容已截断，仅展示前 " \
                f"{MAX_CONTENT_CHARS} 字]*"

        return FetchResult(
            success=True,
            content=content,
            cached=False,
            ai_cleanup_status=ai_status,
        )

    def invalidate(self, article_id: int) -> bool:
        """Clear cached ``full_content`` for ``article_id``.

        Returns ``True`` if a row was actually updated.
        """
        article = self.db.get(NewsArticle, article_id)
        if article is None:
            return False
        article.full_content = None
        article.full_content_fetched_at = None
        try:
            self.db.commit()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ContentFetcher: invalidate commit failed article %s: %s",
                article_id, exc,
            )
            self.db.rollback()
            return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _is_cache_fresh(self, article: NewsArticle) -> bool:
        if not article.full_content or not article.full_content_fetched_at:
            return False
        fetched_at = article.full_content_fetched_at
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        return datetime.now(tz=timezone.utc) - fetched_at < CACHE_TTL

    def _call_jina(self, url: str) -> str:
        """Call Jina Reader and return the Markdown body.

        Raises :class:`_JinaError` on any non-success outcome.
        """
        endpoint = f"{JINA_READER_URL}/{url}"
        headers = {
            # Ask Jina for plain Markdown — the default is fine, but be
            # explicit in case the upstream default changes.
            "Accept": "text/markdown",
            "User-Agent": "AD-Research/1.0 (+https://r.jina.ai)",
        }
        try:
            response = httpx.get(
                endpoint,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
            )
        except httpx.TimeoutException as exc:
            raise _JinaError(f"timeout after {REQUEST_TIMEOUT}s") from exc
        except httpx.HTTPError as exc:
            raise _JinaError(f"http error: {exc}") from exc

        if response.status_code >= 400:
            raise _JinaError(
                f"jina returned http {response.status_code}"
            )

        # Jina prepends the original title and a markdown divider on
        # every response. The downstream renderer is fine with that
        # but it costs cache space — strip the divider if present.
        body = response.text
        if not body:
            return ""
        return body

    def _clean_with_ai(self, content: str) -> tuple[str, str]:
        """Run the AI cleanup step and report its outcome.

        Returns
        -------
        ``(cleaned_text, status)`` where ``status`` is one of:

        * ``"cleaned"``  — DeepSeek returned a non-trivial body. ``cleaned_text``
          is the LLM output.
        * ``"skipped"``  — DeepSeek was not configured (no API key). The
          original Jina Markdown is returned so the reader still gets
          *something*; this is the silent-degradation case the new
          ``ai_cleanup_status`` column makes visible.
        * ``"failed"``   — DeepSeek raised (HTTP 5xx, timeout, rate-limit,
          empty / too-short response). Original Markdown is returned;
          the failure is logged at ``WARNING`` with ``exc_info=True``
          so the ops dashboard can pick it up.
        """
        from app.services.llm import get_llm_provider

        provider = get_llm_provider()
        if not provider.is_available:
            # NOT an error — DeepSeek simply isn't configured in this
            # environment. Still record the attempt so the ops dashboard
            # can tell "AI was on but is rate-limited" from "AI was never
            # on in the first place".
            logger.info("ContentFetcher: AI not available, skipping cleanup")
            return content, "skipped"

        system_prompt = """你是一个文章内容提取助手。你的任务是从网页抓取的原始内容中提取出**真正的正文部分**，去除以下无关内容：
1. 广告（包括图片广告、文字广告、推广链接）
2. 导航菜单、侧边栏、页脚
3. 社交分享按钮、评论区
4. 相关文章推荐
5. 网站版权声明、备案信息
6. 任何与文章正文无关的内容

请直接返回清理后的正文内容，不要添加任何解释、评论或markdown代码块标记。"""

        prompt = f"""请从以下网页抓取内容中提取真正的正文，去除广告、导航、侧边栏等无关内容。只返回正文内容，不要添加任何解释。：\n\n{content[:5000]}"""

        try:
            cleaned = provider.complete(
                prompt=prompt,
                system=system_prompt,
                max_tokens=4000,
                temperature=0.3,
            )
        except Exception as exc:  # noqa: BLE001
            # Surface the stack trace so the "AI failed" alert is
            # actionable in ops — previous behaviour was
            # ``logger.warning("... %s", e)`` which dropped the trace.
            logger.warning(
                "ContentFetcher: AI cleanup raised, keeping original: %s",
                exc,
                exc_info=True,
            )
            return content, "failed"

        if cleaned and len(cleaned) > 100:
            logger.info(
                "ContentFetcher: AI cleanup successful, original length: %d, cleaned: %d",
                len(content), len(cleaned),
            )
            return cleaned, "cleaned"

        # DeepSeek answered but the body is empty / suspiciously short.
        # Treat as a failed cleanup so the yellow/red bar shows up.
        logger.warning(
            "ContentFetcher: AI cleanup returned empty or too short (len=%s), keeping original",
            len(cleaned) if cleaned else 0,
        )
        return content, "failed"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _JinaError(Exception):
    """Wraps any failure from the Jina Reader call so the public API
    stays httpx-agnostic.
    """
