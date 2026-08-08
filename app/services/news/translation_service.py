"""News article translation service.

Calls the configured LLM provider (MiniMax / DeepSeek) to translate the
body (or Jina-fetched ``full_content``) of a non-Chinese
:class:`NewsArticle` into Chinese, then caches the result on the row so
subsequent reads are free.

Design notes
------------
* **Source of truth**: we prefer ``full_content`` over ``body`` when both
  are present, because the Jina-fetched Markdown is the richer text the
  user will actually see on the detail page. Falling back to ``body``
  keeps the endpoint useful for crawlers that haven't filled
  ``full_content`` yet.
* **Language gate**: the service refuses to translate anything whose
  ``language`` is a Chinese variant (``zh``/``zh-tw``/…); every other
  language is translated. This was widened from English-only on
  2026-07-28 for the global multi-language RSS expansion (ja/de/fr/ko/
  es feeds) — the system prompt is multi-language aware, so a Japanese
  or German article translates just as well.
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
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.services.news._model_loader import NewsArticle

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_TRANSLATION_SYSTEM = (
    "你是一名严谨的金融翻译，精通英语、日语、德语、法语、韩语、西班牙语等多种语言。"
    "请将用户提供的资讯正文（原文可能是上述任意一种非中文语言）翻译为中文。\n"
    "要求：\n"
    "1. 保持 Markdown 结构（标题、列表、引用、链接、代码块）原样。\n"
    "2. 保留所有原文专有名词（公司名、产品名、人名、术语首次出现时可附中文译名）。\n"
    "3. 保留所有数字、货币符号、百分比、股票代码、URL。\n"
    "4. 输出纯中文译文，不要附加任何解释、注释或代码块标记。\n"
    "5. 如果原文极短或为空，直接返回空字符串。"
)

# Title translation uses a separate, shorter prompt: the output must be
# a single line of Chinese with no Markdown decoration so it can drop
# straight into the list-page headline slot.
_TITLE_TRANSLATION_SYSTEM = (
    "你是一名严谨的金融翻译，精通英语、日语、德语、法语、韩语、西班牙语等多种语言。"
    "请将用户提供的资讯标题（原文可能是上述任意一种非中文语言）翻译为中文。\n"
    "要求：\n"
    "1. 只输出一行中文标题，不要书名号以外的任何标点装饰、不要解释。\n"
    "2. 保留公司名、产品名、人名等专有名词的原文（可在括号内附中文译名）。\n"
    "3. 保留所有数字、货币符号、百分比、股票代码。\n"
    "4. 如果原文为空，直接返回空字符串。"
)

# Language codes we treat as Chinese (no translation needed). Crawlers
# currently only emit "en" / "zh", but the gate is deliberately
# inclusive so a future ``zh-tw`` / ``cn`` source doesn't get
# double-translated.
_CHINESE_LANGUAGE_CODES: frozenset[str] = frozenset(
    {"zh", "cn", "zh-cn", "zh-hans", "zh-hant", "zh-tw", "zh-hk"}
)

# Retry budget for the auto-translation drain (2026-07-31). A row whose
# translation keeps failing increments ``translation_attempts`` on every
# failed ``auto_translate``; once it reaches this cap the drain stops
# selecting it. Without the cap, ~200 permanently-failing rows
# (paywalled sources with no body text, MiniMax 422 "sensitive"
# rejections) occupied the newest-first batch window indefinitely and
# the 18.7k-row real backlog behind them was never touched — the drain
# reported ``written=200`` per tick while translating nothing.
_MAX_TRANSLATION_ATTEMPTS = 5


class TranslationSensitiveError(RuntimeError):
    """The LLM provider rejected the content as sensitive (HTTP 422).

    MiniMax returns ``input new_sensitive (1026)`` /
    ``output new_sensitive (1027)`` for such requests. The rejection is
    deterministic for a given text, so the caller marks the row as
    permanently skipped (attempts := ``_MAX_TRANSLATION_ATTEMPTS``)
    instead of burning tokens on every drain tick.
    """


def is_chinese_language(language: str | None) -> bool:
    """True when the article language is a Chinese variant.

    ``None`` / unknown codes are treated as *non-Chinese* — the common
    case is English RSS feeds that never set the field, and translating
    an already-Chinese title is only harmful, while translating an
    English one is the whole point. A wrong guess on a genuinely
    non-Chinese, non-English source (rare) still yields a useful Chinese
    rendering.
    """
    return (language or "").strip().lower() in _CHINESE_LANGUAGE_CODES

# Soft cap: 30,000 chars ≈ 8-10k tokens of input. MiniMax / DeepSeek
# both handle this easily; we leave headroom for system prompt +
# output. The rare longer article gets truncated with an explicit
# marker so the reader can see we cut something. Raised from 12k on
# 2026-07-27 — the product requirement is FULL-body translation, and
# 12k was clipping longer Substack / blog essays.
_MAX_INPUT_CHARS = 30_000

# Slow-call budget for a single LLM translation request. Raised from
# 30s on 2026-07-29: full-body translations of long articles legitimately
# take 30-90s, and the old 30s cut-off *discarded the finished response*
# — tokens already spent, row left untranslated, retried and discarded
# again every tick. Long articles were permanently stuck (26% coverage
# for 10k+ vs 53% for <2k). Set to 240s (not 120s) because concurrent
# drain jobs make MiniMax queue server-side: measured single-call
# latency under load is 30-160s (2026-07-29), and anything we discard
# is money already spent. The SDK client timeout is the real backstop.
_MAX_LLM_CALL_SEC = 240.0

# Detect the DeepSeek "no API key configured" placeholder so callers
# can distinguish a real response from the missing-config no-op.
_NO_KEY_HINT = "AI 功能未配置"

# MiniMax / DeepSeek-style models leak reasoning blocks wrapped in
# ``<think>`` into the content field. Strip them before persisting —
# mirrors ``content_fetcher._strip_think_tags`` (kept as a local copy
# to avoid importing the heavy content_fetcher module here).
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_think_tags(text: str) -> str:
    """Remove ``<think>...</think>`` reasoning blocks from LLM output."""
    return _THINK_TAG_RE.sub("", text).strip()


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


def translation_is_stale(article: NewsArticle) -> bool:
    """True when the cached translation was made from a SHORTER source
    than what we have now.

    The classic case (2026-07-27): ingest-time translation ran before
    the full-content fetch finished, so ``translated_zh`` covers only
    the RSS excerpt. When ``full_content`` lands later (10-minute drain
    job or manual fetch), the translation must be redone — the product
    requirement is full-body Chinese, not a translated teaser.
    """
    if not article.translated_zh:
        return False
    if not (article.full_content and article.full_content.strip()):
        return False
    fetched_at = article.full_content_fetched_at
    generated_at = article.translation_generated_at
    if fetched_at and generated_at:
        return fetched_at > generated_at
    # Missing timestamps — can't order the events, assume not stale.
    return False


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

    def translate(
        self, article_id: int, *, target_language: str = "zh", force: bool = False
    ) -> dict[str, Any]:
        """Translate one article; persist the result on the row.

        ``force=True`` bypasses the translation cache — used by the
        drain job when :func:`translation_is_stale` says the cached
        translation was made from a shorter source (e.g. the RSS
        excerpt before the full body arrived).

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
            - Article is already in Chinese (``language`` is a ``zh``
              variant).
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

        if is_chinese_language(article.language):
            raise ValueError(
                f"Article {article_id} language is {article.language!r}; "
                "translation is only enabled for non-Chinese content"
            )

        # Opportunistically fill the Chinese title too — the detail page
        # renders ``title_zh`` as the headline, so a manual translate of
        # an older article should upgrade the title in the same click.
        # Failures here must not block the body translation.
        if not article.title_zh:
            try:
                self.translate_title_if_needed(article)
            except Exception as exc:  # pragma: no cover - defensive
                logger.info("title translation skipped for %s: %s", article_id, exc)
                self.db.rollback()

        if article.translated_zh and not force:
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

        # Call the configured LLM provider (imported lazily so unit tests
        # can patch the factory without paying the OpenAI SDK import cost).
        from app.services.llm import get_llm_provider

        provider = get_llm_provider()
        if not provider.is_available:
            provider_name = type(provider).__name__
            raise RuntimeError(
                f"LLM provider {provider_name} is not available "
                "(API key is not configured on the server)"
            )

        system = _TRANSLATION_SYSTEM
        user = _truncate(source)

        content, tokens = self._call_llm_with_retry(provider, system, user)
        if not content:
            raise RuntimeError(
                f"{type(provider).__name__} returned no usable translation "
                "(timeout, 429 or empty response)"
            )

        # Persist. We use a fresh ``now`` rather than func.now() so the
        # returned ``generated_at`` matches what was actually written.
        now = datetime.now(tz=UTC).replace(tzinfo=None)
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

    # ---- Ingestion-time auto translation ---------------------------------

    def translate_title_if_needed(self, article: NewsArticle) -> str | None:
        """Translate ``article.title`` into ``article.title_zh``.

        No-op (returns the cached value) when ``title_zh`` is already
        set or the article is Chinese. Commits on success; returns
        ``None`` when the LLM call failed — the row is left untouched so
        the next drain tick retries.
        """
        if article.title_zh:
            return article.title_zh
        if is_chinese_language(article.language):
            return None
        if not article.title or not article.title.strip():
            return None

        from app.services.llm import get_llm_provider

        provider = get_llm_provider()
        if not provider.is_available:
            return None

        content, _tokens = self._call_llm_with_retry(
            provider, _TITLE_TRANSLATION_SYSTEM, article.title.strip()
        )
        if not content:
            return None
        # Defensive: titles must stay one line for the list page.
        title_zh = content.strip().splitlines()[0].strip() if content.strip() else ""
        if not title_zh:
            return None
        article.title_zh = title_zh[:1000]
        self.db.commit()
        return article.title_zh

    def auto_translate(self, article_id: int) -> dict[str, Any]:
        """Best-effort full translation for the ingestion pipeline.

        Unlike :meth:`translate` this **never raises** — it is called
        from the crawler write path where a translation failure must not
        break persistence. Translates the title (when missing) and the
        body (when missing) for any non-Chinese article.

        Returns ``{"article_id", "skipped", "reason", "title_zh",
        "title_new", "translated", "cached"}``:

        * ``skipped=True`` (with ``reason``) for Chinese articles,
          missing rows, and rows with nothing left to translate
          (``reason="nothing_to_do"`` — title already cached and no
          source text for the body).
        * ``translated=True`` only when the BODY was **newly**
          translated this call; ``title_new=True`` only when the TITLE
          was newly translated. Callers must aggregate on these two
          flags — counting a cached title as fresh work is what made
          the drain report ``written=200`` per tick while spinning on
          untranslatable rows (2026-07-31 poison-queue incident, see
          ``docs/dev-notes/20260731-translation-drain-poison-queue.md``).

        Failure bookkeeping: when the row still needed work and nothing
        succeeded, ``translation_attempts`` is incremented (jumping
        straight to ``_MAX_TRANSLATION_ATTEMPTS`` for deterministic
        sensitive-content rejections); the drain stops selecting rows
        at the cap.
        """
        article = self.db.get(NewsArticle, article_id)
        if article is None:
            return {"article_id": article_id, "skipped": True, "reason": "not_found"}
        if is_chinese_language(article.language):
            return {"article_id": article_id, "skipped": True, "reason": "chinese"}

        had_title = bool(article.title_zh)
        stale = translation_is_stale(article)
        has_text = _pick_source(article) is not None
        work_to_do = (not had_title) or (
            has_text and (not article.translated_zh or stale)
        )
        if not work_to_do:
            # E.g. title already translated but the source has no body
            # text (paywalled excerpt-only feeds). Reported as skipped
            # so the batch stats only count real new translations.
            return {
                "article_id": article_id,
                "skipped": True,
                "reason": "nothing_to_do",
                "title_zh": None,
                "title_new": False,
                "translated": False,
                "cached": True,
            }

        sensitive = False
        title_zh = None
        try:
            title_zh = self.translate_title_if_needed(article)
        except TranslationSensitiveError as exc:
            sensitive = True
            logger.warning(
                "auto title translation blocked for %s: %s", article_id, exc
            )
            self.db.rollback()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("auto title translation failed for %s: %s", article_id, exc)
            self.db.rollback()

        body_status: dict[str, Any] = {"cached": False, "translated": False}
        if article.translated_zh and not stale:
            # Body already done — the row was only here for the title.
            body_status = {"cached": True, "translated": False}
        elif has_text:
            try:
                self.translate(article_id, force=stale)
                body_status = {"cached": False, "translated": True}
            except TranslationSensitiveError as exc:
                sensitive = True
                logger.warning(
                    "auto body translation blocked for %s: %s", article_id, exc
                )
                self.db.rollback()
            except Exception as exc:
                logger.info("auto body translation failed for %s: %s", article_id, exc)
                self.db.rollback()

        title_new = bool(title_zh) and not had_title
        succeeded = title_new or body_status["translated"]
        self._record_attempt_outcome(article, succeeded=succeeded, sensitive=sensitive)

        return {
            "article_id": article_id,
            "skipped": False,
            "title_zh": title_zh,
            "title_new": title_new,
            **body_status,
        }

    def _record_attempt_outcome(
        self, article: NewsArticle, *, succeeded: bool, sensitive: bool
    ) -> None:
        """Update ``translation_attempts`` after an auto-translate pass.

        Best-effort, never raises. On success the counter resets so a
        future stale re-translation gets a fresh budget; on failure it
        increments, and deterministic sensitive-content rejections jump
        straight to the cap so the drain never selects the row again.
        """
        try:
            if succeeded:
                if article.translation_attempts:
                    article.translation_attempts = 0
                    self.db.commit()
            else:
                if sensitive:
                    article.translation_attempts = _MAX_TRANSLATION_ATTEMPTS
                else:
                    article.translation_attempts = (
                        article.translation_attempts or 0
                    ) + 1
                self.db.commit()
        except Exception as exc:  # pragma: no cover - defensive
            logger.info(
                "translation_attempts update failed for %s: %s", article.id, exc
            )
            self.db.rollback()

    # ---- LLM helpers ----------------------------------------------------

    def _call_llm_with_retry(
        self, provider, system: str, user: str
    ) -> tuple[str | None, int | None]:
        """Single LLM call with one 429 retry.

        Returns ``(content, tokens_used)``. ``tokens_used`` is reported
        as ``None`` when the provider isn't configured or the call fails —
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
                if elapsed > _MAX_LLM_CALL_SEC:
                    logger.warning(
                        "News translation LLM call took %.2fs (>%.0fs); skipping",
                        elapsed,
                        _MAX_LLM_CALL_SEC,
                    )
                    return None, None
                if not content:
                    return None, None
                # Strip reasoning blocks before anything else — a
                # response that is *only* a think block (model spent
                # its whole budget reasoning) reduces to empty and is
                # treated as a failed call, not persisted.
                content = _strip_think_tags(content)
                if not content:
                    logger.info("News translation LLM returned only a think block; skipping")
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
                if "sensitive" in msg:
                    # Deterministic rejection (MiniMax 422) — retrying
                    # the same text can never succeed, so surface it as
                    # a dedicated error instead of a silent None: the
                    # auto pipeline marks the row permanently skipped.
                    logger.warning(
                        "News translation blocked by sensitive-content filter: %s",
                        exc,
                    )
                    raise TranslationSensitiveError(str(exc)) from exc
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
