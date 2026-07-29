"""News article one-sentence Chinese summary service (方向 D, 2026-07-29).

Calls the configured LLM provider (MiniMax / DeepSeek via
:func:`app.services.llm.get_llm_provider`) to compress a
:class:`NewsArticle` — title + body / ``full_content`` — into a single
Chinese sentence (≤80 字) persisted on ``summary_zh`` so the news feed
can render a digest line under each headline without an on-demand LLM
call.

Design notes
------------
* **Language-agnostic**: unlike the translation pipeline there is NO
  Chinese gate. A summary is not a title restated — a Chinese headline
  still gets a digest line, so the drain job feeds every language.
* **Source of truth**: prefers ``full_content`` over ``body`` (same
  rationale as ``translation_service._pick_source``), truncated to a
  small input cap — a one-line summary does not need the full 30k-char
  body, and smaller inputs keep the per-call token cost low.
* **Caching**: ``summary_zh`` doubles as the "did we already summarize
  this" sentinel; the drain job only selects rows where it is NULL.
* **Failure modes**: provider unavailable / timeout / 429 all return
  ``None`` and leave the row untouched so the next drain tick retries —
  mirrors the translation service's fail-safe contract.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.services.news._model_loader import NewsArticle
from app.services.news.translation_service import (
    _NO_KEY_HINT,
    _strip_think_tags,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

# Hard output cap enforced client-side as well (``_enforce_shape``) — the
# prompt asks for ≤80 字 but models occasionally overshoot, and the feed
# renders this as a single line.
MAX_SUMMARY_CHARS = 80

_SUMMARY_SYSTEM = (
    "你是一名严谨的金融资讯编辑。请根据用户提供的资讯标题与正文，输出一句话中文摘要。\n"
    "要求：\n"
    "1. 只输出一句话，不超过 80 个汉字。\n"
    "2. 客观陈述事实，保留关键数字、日期、金额、百分比、公司名。\n"
    "3. 不使用评价性词汇（如“重磅”“震惊”“利好”“值得关注”）。\n"
    "4. 不要复述标题——摘要必须提供标题之外的信息增量。\n"
    "5. 不要输出任何解释、前缀（如“摘要：”）、引号或书名号。\n"
    "6. 如果正文为空或与标题完全相同，直接返回空字符串。"
)

# Input cap: 4,000 chars ≈ 1.5-2k tokens. A one-sentence summary needs
# the lead, not the whole essay — and 65+ sources × ~1,000 articles/day
# makes the input-token side the dominant cost, so we keep it tight.
_MAX_INPUT_CHARS = 4_000


def _truncate_input(text: str) -> str:
    """Cap the source text fed to the LLM (cost control)."""
    if len(text) <= _MAX_INPUT_CHARS:
        return text
    return text[: _MAX_INPUT_CHARS - 20].rstrip() + " …"


def _pick_source(article: NewsArticle) -> str | None:
    """Pick the best source text: ``full_content`` → ``body`` → ``summary``."""
    for text in (article.full_content, article.body, article.summary):
        if text and text.strip():
            return text
    return None


def _enforce_shape(text: str) -> str:
    """Force the LLM output into the single-line ≤80-char contract.

    Strips think tags (already done by the caller), takes the first
    non-empty line, drops decorative quotes / prefixes, and hard-cuts at
    ``MAX_SUMMARY_CHARS`` with an ellipsis so a chatty model can never
    break the one-line feed layout.
    """
    line = ""
    for candidate in text.strip().splitlines():
        candidate = candidate.strip()
        if candidate:
            line = candidate
            break
    # Drop common self-labelling prefixes the prompt forbids but models
    # sometimes emit anyway.
    for prefix in ("摘要：", "摘要:", "总结：", "总结:"):
        if line.startswith(prefix):
            line = line[len(prefix):].strip()
    line = line.strip("“”\"'")
    if len(line) > MAX_SUMMARY_CHARS:
        line = line[: MAX_SUMMARY_CHARS - 1].rstrip("，。、；,.; ") + "…"
    return line


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class NewsSummaryService:
    """Generate one-sentence Chinese summaries for news articles.

    Holds a DB session and writes the result back to the
    ``NewsArticle`` row. Stateless apart from ``self.db``; safe to
    instantiate per drain tick.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- Public API -----------------------------------------------------

    def summarize(self, article_id: int, *, force: bool = False) -> dict[str, Any]:
        """Summarize one article; persist the result on ``summary_zh``.

        Returns ``{article_id, skipped, reason?, summary?}`` —
        ``skipped=True`` (with ``reason``) for missing rows, cached rows
        (unless ``force``), articles with no usable source text, or an
        unavailable / failing provider. Never raises: it runs inside the
        drain job where a single bad row must not abort the batch.
        """
        article = self.db.get(NewsArticle, article_id)
        if article is None:
            return {"article_id": article_id, "skipped": True, "reason": "not_found"}

        if article.summary_zh and not force:
            return {
                "article_id": article_id,
                "skipped": True,
                "reason": "cached",
                "summary": article.summary_zh,
            }

        if not article.title or not article.title.strip():
            return {"article_id": article_id, "skipped": True, "reason": "no_title"}

        source = _pick_source(article)
        if not source:
            # Title-only articles can't yield a summary with any
            # information increment over the headline — skip rather than
            # burn tokens on a title paraphrase.
            return {"article_id": article_id, "skipped": True, "reason": "no_body"}

        from app.services.llm import get_llm_provider

        provider = get_llm_provider()
        if not provider.is_available:
            return {
                "article_id": article_id,
                "skipped": True,
                "reason": "provider_unavailable",
            }

        user = f"标题：{article.title.strip()}\n\n正文：{_truncate_input(source)}"
        content, _tokens = self._call_llm_with_retry(provider, _SUMMARY_SYSTEM, user)
        if not content:
            return {"article_id": article_id, "skipped": True, "reason": "llm_failed"}

        summary = _enforce_shape(content)
        if not summary:
            return {"article_id": article_id, "skipped": True, "reason": "empty_output"}

        article.summary_zh = summary[:500]
        self.db.commit()
        return {
            "article_id": article_id,
            "skipped": False,
            "summary": article.summary_zh,
        }

    # ---- LLM helpers ----------------------------------------------------

    def _call_llm_with_retry(
        self, provider, system: str, user: str
    ) -> tuple[str | None, int | None]:
        """Single LLM call with one 429 retry — mirrors
        ``NewsTranslationService._call_llm_with_retry``."""
        for attempt in range(2):
            try:
                start = time.monotonic()
                content = provider.chat(
                    messages=[{"role": "user", "content": user}],
                    system=system,
                )
                elapsed = time.monotonic() - start
                # 2026-07-29: 30s -> 120s, mirroring translation_service's
                # _MAX_LLM_CALL_SEC. Under concurrent drain load MiniMax
                # legitimately takes 30-160s per call; with the old 30s
                # guard every batch was fully discarded AFTER the tokens
                # were spent (etl_log all-"skipped", summaries stalled at
                # ~110 rows while 5k+ queued). The 600s tick budget in
                # run_summarize_pending still bounds total work per tick.
                if elapsed > 120.0:
                    logger.warning(
                        "News summary LLM call took %.2fs (>120s); skipping",
                        elapsed,
                    )
                    return None, None
                if not content:
                    return None, None
                content = _strip_think_tags(content)
                if not content:
                    logger.info("News summary LLM returned only a think block; skipping")
                    return None, None
                if _NO_KEY_HINT in content:
                    logger.info("News summary LLM: no API key configured, skipping")
                    return None, None
                return content.strip(), None
            except Exception as exc:
                msg = str(exc).lower()
                is_429 = "429" in msg or "rate" in msg
                if is_429 and attempt == 0:
                    logger.warning("News summary LLM 429; retrying in 2s")
                    time.sleep(2.0)
                    continue
                logger.warning("News summary LLM call failed: %s", exc)
                return None, None
        return None, None
