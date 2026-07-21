"""Fetch full article body with a tiered extraction pipeline.

The fetcher turns a ``news_article.url`` into a clean, boilerplate-free
body stored in ``news_article.full_content`` so the detail page renders
immediately. Extraction tiers, in order:

1. **Local trafilatura** — download the page with httpx and extract the
   main content locally. Free, fast, no external rate limit, and
   purpose-built for stripping navigation/ads/related-links.
2. **Jina Reader** (``r.jina.ai``) — external fallback when the local
   extraction finds nothing (JS-heavy pages, anti-bot HTML).
3. **LLM-from-HTML** — when both deterministic tiers fail, hand the
   stripped page text to the configured LLM provider and ask for the
   article body only. Controlled by
   ``settings.news_content_llm_fallback``.

Flow
----
1. Check ``news_article.full_content`` + ``full_content_fetched_at``.
   If the cache is fresh (< 24h) return it as-is.
2. Run the tiers above until one yields a body, then clean the result
   deterministically (strip repeated titles / metadata / navigation
   noise) and store it back to the DB.
3. On any failure at every tier, log it and return ``None`` — the
   caller then falls back to the original ``body`` (the RSS summary
   already available).

The 24-hour TTL is enforced by the caller; the fetcher itself just
re-fetches whenever invoked. That keeps the service unit-testable and
avoids time-of-day decisions inside the module.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.news._model_loader import NewsArticle

logger = logging.getLogger(__name__)

# Public Jina Reader endpoint. Free for personal use, no API key.
JINA_READER_URL: Final[str] = "https://r.jina.ai"

# 30-second timeout per request — Jina can be slow on large pages.
REQUEST_TIMEOUT: Final[float] = 30.0

# Direct HTML download (tier 1) uses a shorter timeout — origin servers
# are usually fast, and a slow one just means we fall through to Jina.
HTML_REQUEST_TIMEOUT: Final[float] = 20.0

# Browser-like UA for direct page downloads; several CN finance sites
# 403 generic HTTP-client agents.
_HTML_USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

# Cap on the stripped page text handed to the LLM fallback tier.
_LLM_MAX_INPUT_CHARS: Final[int] = 8000

# The LLM fallback must return at least this fraction of its input
# (before cleaning) — a much shorter answer usually means the model
# summarised instead of extracting.
_LLM_MIN_OUTPUT_RATIO: Final[float] = 0.15

# Minimum meaningful body length after deterministic cleanup. If the
# cleaned body is shorter than this, we fall back to the raw Jina
# Markdown so the user still has something to read.
# 20 was too strict (review-news-analyst P0-5): short news flashes and
# Jina's truncated excerpts were rejected, showing a red `failed` Alert
# on every detail page. 80 chars roughly maps to "one meaningful sentence".
MIN_BODY_LENGTH: Final[int] = 80

# Hard cap on stored content to keep the DB row reasonable.
MAX_CONTENT_CHARS: Final[int] = 10_000

# Cache TTL applied by callers when deciding whether to re-fetch.
CACHE_TTL: Final[timedelta] = timedelta(hours=24)

# ---------------------------------------------------------------------------
# Deterministic Jina-body cleaners
# ---------------------------------------------------------------------------

# Structured plain-text response from Jina separates headers from the
# actual Markdown body. Example:
#   Title: ...
#   URL Source: ...
#   Published Time: ...
#   Markdown Content:
#   # ...
_MARKDOWN_SECTION_RE: Final[re.Pattern[str]] = re.compile(
    r"^Markdown Content:\s*\n(.*)",
    re.DOTALL | re.MULTILINE,
)

# Date / source / author metadata that Jina often leaves at the top of
# the Markdown body after the title.
_METADATA_RE: Final[re.Pattern[str]] = re.compile(
    r"^(\s*"
    r"(\d{4}[\-/年]\d{1,2}[\-/月]\d{1,2}[日]?\s*(\d{1,2}:\d{2})?)"
    r"|(.*\d{4}[\-/年]\d{1,2}[\-/月]\d{1,2}[日]?.*)"
    r"|(发表于.*)"
    r"|(来源[：:].*)"
    r"|(作者[：:].*)"
    r"|(编辑[：:].*)"
    r"|(阅读[：:]\s*\d+)"
    r"|(.*\d+次浏览)"
    r"|(.*记者.*)"
    r"|(.*日报.*)"
    r"\s*)$",
    re.IGNORECASE,
)

# Navigation / footer / boilerplate lines that are not article body.
_BOILERPLATE_RE: Final[re.Pattern[str]] = re.compile(
    r"^("
    r"更多阅读|相关阅读|推荐阅读|延伸阅读|相关文章|热门文章|热门推荐"
    r"|返回首页|返回列表|返回顶部|上一篇|下一篇|文章分类"
    r"|分享到[:：]?.*|收藏|打印|字号|相关稿件|我要纠错|扫一扫"
    r"|免责声明|版权所有|备案|京ICP备|京公网安备|网站标识码"
    r"|原文链接|查看原文|点击阅读|阅读全文|展开全文"
    r"|责任编辑[:：]?.*|值班编辑[:：]?.*|审核[:：]?.*"
    r"|VIP课程推荐|APP专享.*|收起"
    r"|https?://\S+"
    r")$",
    re.IGNORECASE,
)

# Short promo / call-to-action lines (follow-us, QR-code, fan perks).
# Only matched on standalone short lines so a legitimate in-body
# sentence mentioning 扫码 is not nuked.
_PROMO_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"扫描二维码|扫码关注|粉丝福利|关注公众号|关注我们|微信扫码|"
    r"扫码下载|下载客户端|打开APP|打开App"
)
_PROMO_LINE_MAX_LEN: Final[int] = 60

# Some DeepSeek-style models leak reasoning blocks wrapped in <think>.
_THINK_TAG_RE: Final[re.Pattern[str]] = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think_tags(text: str) -> str:
    """Remove any ``<think>...</think>`` reasoning blocks from LLM output."""
    return _THINK_TAG_RE.sub("", text)


def _extract_markdown_section(raw: str) -> str:
    """Return the ``Markdown Content:`` section from Jina's plain-text response.

    If the response is already plain Markdown (no headers), return it as-is.
    """
    raw = raw.replace("\r\n", "\n")
    m = _MARKDOWN_SECTION_RE.search(raw)
    if m:
        return m.group(1).strip()
    return raw.strip()


def _strip_leading_title_and_metadata(text: str, title: str) -> str:
    """Remove the repeated title, date, source and author lines at the top.

    Stops as soon as it encounters a non-metadata line so that real short
    headings inside the body are preserved.
    """
    if not text:
        return text

    lines = text.splitlines()
    title_norm = _normalize_text(title)
    start = 0

    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped:
            start = i + 1
            continue

        # Heading that matches the article title.
        heading = re.sub(r"^#+\s*", "", stripped).strip()
        if _normalize_text(heading) == title_norm:
            start = i + 1
            continue

        # Any date / source / author metadata line.
        if _METADATA_RE.match(stripped):
            start = i + 1
            continue

        # Standalone URL right under the title is also header noise.
        if stripped.startswith(("http://", "https://")):
            start = i + 1
            continue

        # Looks like a real paragraph / heading — stop stripping.
        break

    return "\n".join(lines[start:])


def _remove_duplicate_title(text: str, title: str) -> str:
    """Remove any later standalone occurrence of the article title."""
    if not title or not text:
        return text

    escaped = re.escape(title)
    # Match title as a plain line or as a markdown heading.
    pattern = re.compile(r"^\s*#?\s*" + escaped + r"\s*$", re.MULTILINE | re.IGNORECASE)
    text = pattern.sub("", text)
    # Collapse the blank lines left behind.
    return re.sub(r"\n{3,}", "\n\n", text)


def _strip_boilerplate_lines(text: str) -> str:
    """Drop navigation/footer lines and standalone image/link cruft."""
    if not text:
        return text

    lines_out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            lines_out.append("")
            continue

        # Match boilerplate on the de-marked form: "## 热门推荐" and
        # "*收起*" are the same noise as their plain-text variants.
        probe = re.sub(r"^#+\s*", "", stripped).strip("* ").strip()

        if _BOILERPLATE_RE.match(stripped) or (probe and _BOILERPLATE_RE.match(probe)):
            continue

        # Short promo / call-to-action lines (QR-code, follow-us).
        if len(stripped) <= _PROMO_LINE_MAX_LEN and _PROMO_LINE_RE.search(stripped):
            continue

        # Standalone markdown link (likely a nav button).
        if re.match(r"^!?\[[^\]]+\]\([^)]+\)$", stripped):
            continue

        # Breadcrumb lines made of links separated by > / | / -.
        if re.match(
            r"^(\[[^\]]+\]\([^)]+\)\s*[>|\-/]\s*)+\[[^\]]+\]\([^)]+\)$",
            stripped,
        ):
            continue

        # Empty bullet separators: "*", "-", "* |", "- -"
        if re.match(r"^[\*\-•]\s*[|\-—\s]*$", stripped):
            continue

        lines_out.append(line)

    return "\n".join(lines_out).strip()


def _normalize_text(text: str) -> str:
    """Normalize text for comparison: lower-case, collapse whitespace."""
    return re.sub(r"\s+", "", text.strip().lower())


def _clean_jina_body(raw: str, title: str) -> str:
    """Deterministic cleanup of an extracted Markdown body.

    Handles output from any extraction tier (trafilatura, Jina Reader,
    LLM): strips repeated titles and metadata, removes navigation /
    footer lines, and de-duplicates paragraphs. The result is the real
    article body without calling an LLM.
    """
    text = _strip_think_tags(raw)
    text = _extract_markdown_section(text)
    text = _strip_leading_title_and_metadata(text, title)
    text = _remove_duplicate_title(text, title)
    text = _strip_boilerplate_lines(text)

    # De-duplicate exact paragraphs that sometimes appear twice (e.g.
    # gov.cn / 21st Century Business Herald renders).
    seen: set[str] = set()
    paragraphs: list[str] = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        norm = _normalize_text(para)
        if norm and norm in seen:
            continue
        seen.add(norm)
        paragraphs.append(para)

    return "\n\n".join(paragraphs).strip()


# ---------------------------------------------------------------------------
# Tier 1 / 3 helpers — local extraction and LLM fallback
# ---------------------------------------------------------------------------

_SCRIPT_STYLE_RE: Final[re.Pattern[str]] = re.compile(
    r"<(script|style|noscript)[^>]*>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)
_HTML_COMMENT_RE: Final[re.Pattern[str]] = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_TAG_RE2: Final[re.Pattern[str]] = re.compile(r"<[^>]+>")
_WS_RE: Final[re.Pattern[str]] = re.compile(r"[ \t]+")


def _html_to_text(html: str) -> str:
    """Strip raw HTML down to readable text for the LLM fallback tier."""
    text = _SCRIPT_STYLE_RE.sub(" ", html)
    text = _HTML_COMMENT_RE.sub(" ", text)
    text = _HTML_TAG_RE2.sub("\n", text)
    lines = [_WS_RE.sub(" ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _extract_with_trafilatura(html: str, url: str) -> str | None:
    """Tier 1: extract the main article body locally via trafilatura.

    Returns Markdown-ish text, or ``None`` when trafilatura cannot find
    a real body (JS shells, anti-bot pages, non-article HTML).
    """
    try:
        import trafilatura
    except ImportError:  # pragma: no cover - dependency is declared
        logger.warning("ContentFetcher: trafilatura not installed, skipping local tier")
        return None
    try:
        return trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_comments=False,
            include_tables=False,
            include_links=False,
            include_images=False,
            favor_precision=True,
            deduplicate=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("ContentFetcher: trafilatura failed for %s: %s", url, exc)
        return None


_LLM_EXTRACT_SYSTEM: Final[str] = (
    "你是一个网页正文抽取器。输入是一篇新闻网页去掉 HTML 标签后的全文"
    "（可能混有导航、广告、推荐链接、版权信息等噪音）。"
    "你的任务：只输出新闻正文本身，剔除所有与正文无关的内容"
    "（导航、页眉页脚、相关阅读、推广、免责声明、按钮文字等）。"
    "要求：保留正文原始措辞，禁止总结、改写、翻译或添加任何评论；"
    "保留自然段落结构；不要输出 ``` 代码块或任何前后缀说明。"
)


def _extract_with_llm(page_text: str, title: str) -> str | None:
    """Tier 3: ask the configured LLM provider to isolate the body.

    The output is validated (length floor, think-tag strip) and still
    goes through the deterministic cleaner afterwards, so a hallucinated
    or truncated answer degrades to a plain fetch failure instead of
    poisoning the cache.
    """
    try:
        from app.services.llm import get_llm_provider

        provider = get_llm_provider()
        if not provider.is_available:
            return None
        prompt = (
            f"文章标题：{title}\n\n"
            f"网页全文（已去标签，可能含噪音）：\n{page_text[:_LLM_MAX_INPUT_CHARS]}\n\n"
            "请只输出该新闻的正文内容。"
        )
        output = provider.complete(
            prompt,
            system=_LLM_EXTRACT_SYSTEM,
            max_tokens=4096,
            temperature=0.0,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ContentFetcher: llm extraction failed: %s", exc)
        return None

    if not output:
        return None
    output = _strip_think_tags(output).strip()
    # Strip a markdown code fence if the model wrapped the answer anyway.
    if output.startswith("```"):
        output = re.sub(r"^```[a-zA-Z]*\n?", "", output)
        output = re.sub(r"\n?```$", "", output).strip()
    if len(output) < MIN_BODY_LENGTH:
        return None
    if len(output) < len(page_text[:_LLM_MAX_INPUT_CHARS]) * _LLM_MIN_OUTPUT_RATIO:
        logger.info(
            "ContentFetcher: llm output too short relative to input (%d vs %d), rejected",
            len(output), len(page_text),
        )
        return None
    return output


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

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
    # ``ai_cleanup_status`` keeps whatever value it already had so we do
    # not stomp a historical success.
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

        # 2) Tiered extraction: local trafilatura → Jina Reader → LLM.
        md: str | None = None
        method: str | None = None
        last_error = "all extraction tiers failed"

        html = self._fetch_html(article.url)
        if html:
            md = _extract_with_trafilatura(html, article.url)
            if md:
                method = "trafilatura"

        if not md:
            try:
                md = self._call_jina(article.url)
                if md:
                    method = "jina"
                else:
                    last_error = "empty response from Jina Reader"
            except _JinaError as exc:
                last_error = str(exc)
                logger.warning(
                    "ContentFetcher: jina failed for article %s url=%s: %s",
                    article_id, article.url, exc,
                )

        if not md and html and get_settings().news_content_llm_fallback:
            md = _extract_with_llm(_html_to_text(html), article.title)
            if md:
                method = "llm"

        if not md:
            logger.warning(
                "ContentFetcher: no body extracted for article %s url=%s: %s",
                article_id, article.url, last_error,
            )
            return FetchResult(success=False, content=None, cached=False,
                               error=last_error)

        logger.info(
            "ContentFetcher: extracted body for article %s via %s",
            article_id, method,
        )

        # 3) Clean the extracted Markdown deterministically (no LLM). This
        # avoids the <think> / duplicate-title / no-body problems we saw
        # with the DeepSeek extraction prompt.
        cleaned = _clean_jina_body(md, article.title)

        # 4) Validate the cleaned body. If it is too short, treat the
        # fetch as a soft failure: report it back, record the status for
        # the ops dashboard, and DO NOT cache the useless raw Jina
        # Markdown (it would just show the title + date and no body).
        # The API layer will fall back to ``article.summary`` / ``body``.
        if len(cleaned) < MIN_BODY_LENGTH:
            logger.warning(
                "ContentFetcher: cleaned body too short for article %s (len=%d), "
                "treating as extraction failure",
                article_id, len(cleaned),
            )
            article.ai_cleaned_at = datetime.now(tz=UTC)
            article.ai_cleanup_status = "failed"
            try:
                self.db.commit()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ContentFetcher: db commit failed for article %s: %s",
                    article_id, exc,
                )
                self.db.rollback()
            return FetchResult(
                success=False,
                content=article.summary or article.body,
                cached=False,
                error=(
                    "Jina returned a near-empty body (likely missing the main "
                    "article text); kept the summary as fallback"
                ),
                ai_cleanup_status="failed",
            )

        content = cleaned
        ai_status = "cleaned"

        # 5) Safety truncate.
        truncated = False
        if len(content) > MAX_CONTENT_CHARS:
            content = content[:MAX_CONTENT_CHARS]
            truncated = True
            logger.info(
                "ContentFetcher: truncated article %s to %d chars",
                article_id, MAX_CONTENT_CHARS,
            )

        # 6) Store back to DB, including the cleanup status.
        article.full_content = content
        article.full_content_fetched_at = datetime.now(tz=UTC)
        article.ai_cleaned_at = datetime.now(tz=UTC)
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
            fetched_at = fetched_at.replace(tzinfo=UTC)
        return datetime.now(tz=UTC) - fetched_at < CACHE_TTL

    def _fetch_html(self, url: str) -> str | None:
        """Download the raw page HTML for the local / LLM tiers.

        Returns ``None`` on any network or HTTP failure — the caller
        simply falls through to the next tier.
        """
        try:
            response = httpx.get(
                url,
                headers={"User-Agent": _HTML_USER_AGENT},
                timeout=HTML_REQUEST_TIMEOUT,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            logger.debug("ContentFetcher: html download failed for %s: %s", url, exc)
            return None
        if response.status_code >= 400:
            logger.debug(
                "ContentFetcher: html download http %s for %s",
                response.status_code, url,
            )
            return None
        return response.text or None

    def _call_jina(self, url: str) -> str:
        """Call Jina Reader and return the Markdown body.

        We ask for ``text/plain`` so Jina returns the structured header
        block (Title, URL Source, Published Time, Markdown Content) which
        makes it easy to separate the real article body from page
        metadata.

        Raises :class:`_JinaError` on any non-success outcome.
        """
        endpoint = f"{JINA_READER_URL}/{url}"
        headers = {
            # Ask Jina for plain text with the structured header block.
            # The Markdown body lives under ``Markdown Content:``.
            "Accept": "text/plain",
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

        return response.text or ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _JinaError(Exception):
    """Wraps any failure from the Jina Reader call so the public API
    stays httpx-agnostic.
    """
