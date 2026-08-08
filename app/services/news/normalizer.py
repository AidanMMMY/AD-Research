"""Normalize :class:`RawArticle` payloads into the ORM rows.

The single entry point is :meth:`NewsNormalizer.normalize`. It:

1. Builds the stable dedup key (``source + source_id``).
2. Performs an UPSERT (skip-if-exists) — when an article with the
   same key already exists, returns ``None`` so the caller can
   count it as a no-op.
3. Persists the article row and the matched symbol rows in one
   transaction. The commit is left to the caller so a batch of
   normalizations can share a single round-trip.

The normalizer never raises. Any unexpected per-article failure is
logged and the function returns ``None``; the caller (typically the
crawler's ``run`` method) keeps going.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from simhash import Simhash
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.etf import ETFInfo
from app.services.news._model_loader import NewsArticle, NewsArticleSymbol
from app.services.news.crawler.types import RawArticle
from app.services.news.symbol_extractor import SymbolExtractor
from app.services.news.zh_convert import convert_article_text_fields

logger = logging.getLogger(__name__)


def _hash_text(value: str | None) -> str | None:
    """Return md5(value) as a 32-char hex string, or ``None`` for empty input."""
    if not value:
        return None
    return hashlib.md5(value.encode("utf-8", errors="ignore")).hexdigest()


# 未来时间钳制（2026-08-01 生产事故加固）：部分 feed 的时间戳标注错误
# （如 nocutnews 把韩国本地墙钟时间标成 GMT，入库后比真实 UTC 快 9 小时，
# 前端 +8 显示成"未来时间"），也有 CMS 定时发布/时钟漂移导致 pubDate
# 略超当前时间的情况。源层修复（rss_common tz_override）只能覆盖已知
# 坏 feed，这里是新闻写入的唯一汇合点，统一把超过 now+15min 的
# published_at 钳到 now —— 15 分钟容忍窗口覆盖合理的时钟漂移与定时
# 发布，超出即视为脏数据。钳制会打 warning 日志，便于发现新的坏 feed。
_FUTURE_TOLERANCE = timedelta(minutes=15)


def _clamp_future_published_at(ts: datetime, *, source: str) -> datetime:
    """Clamp future ``published_at`` to now (with a 15-minute tolerance)."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    now = datetime.now(tz=UTC)
    if ts > now + _FUTURE_TOLERANCE:
        logger.warning(
            "normalize: %s published_at %s 超前当前时间超过 %s，已钳制到 now",
            source,
            ts.isoformat(),
            _FUTURE_TOLERANCE,
        )
        return now
    return ts


def _simhash_text(value: str | None) -> str | None:
    """Return a 64-bit simhash of ``value`` as a decimal string, or ``None``.

    The value is stored as a plain integer string so downstream dedup code
    can rebuild a :class:`simhash.Simhash` directly without parsing a hex
    prefix.  64-bit simhash fits comfortably in a 20-char decimal string.
    """
    if not value:
        return None
    try:
        return str(Simhash(value.strip()).value)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("simhash failed: %s", exc)
        return None


def _safe_json(value: Any) -> dict | list | None:
    """Return a JSON-safe dict/list for the engagement column.

    Falls back to a string repr if the value isn't natively
    serializable, so the JSON column never breaks.
    """
    if value is None or value == "":
        return {}
    if isinstance(value, dict | list):
        return value
    if isinstance(value, str):
        try:
            data = json.loads(value)
            if isinstance(data, dict | list):
                return data
        except (TypeError, ValueError):
            return {"raw": value[:1000]}
    try:
        return {"raw": json.dumps(value, default=str, ensure_ascii=False)[:1000]}
    except Exception:  # noqa: BLE001
        return None


class NewsNormalizer:
    """Map :class:`RawArticle` → DB rows in ``news_article`` and friends.

    The :class:`SymbolExtractor` is instantiated lazily and cached for
    the lifetime of the normalizer (which is typically the lifetime of
    the scheduler job — a few seconds). The instance is not safe to
    share across threads.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._extractor: SymbolExtractor | None = None

    @property
    def symbol_extractor(self) -> SymbolExtractor:
        if self._extractor is None:
            self._extractor = SymbolExtractor(self.db)
        return self._extractor

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def normalize(self, raw: RawArticle) -> NewsArticle | None:
        """Return a fresh :class:`NewsArticle` (added to the session).

        Returns ``None`` when:

        * The article's ``(source, source_id)`` already exists in the
          database (duplicate).
        * The article is missing required fields.
        * Any unexpected exception happens during normalization.

        Caller is responsible for ``db.commit()``.
        """
        try:
            if not raw.title or not raw.url:
                logger.debug("normalize: skip empty raw url=%s", raw.url)
                return None

            # 1) Dedup on (source, source_id).
            source_id = raw.source_id or raw.url
            existing = self.db.execute(
                select(NewsArticle.id).where(
                    NewsArticle.source == raw.source,
                    NewsArticle.source_id == source_id,
                )
            ).first()
            if existing is not None:
                return None

            # 2) Build the article row.
            full_body = raw.body or _strip_html_to_text(raw.body_html)
            language = raw.language or "zh"
            # 繁→简转换（2026-08-01）：台湾/香港中文源（zhb_/zhx_/部分
            # wechat_）正文是繁体；入库时统一转简体，避免读路径/前端
            # 逐条转换。仅对中文文章且检出繁体特征时生效，已是简体的
            # 文本原样通过。截断在转换之后做，避免把转换后的字符切半。
            converted = convert_article_text_fields(
                {"title": raw.title, "body": full_body},
                language=language,
            )
            title = (converted["title"] or raw.title)[:1000]
            full_body = converted["body"]
            article = NewsArticle(
                source=raw.source,
                source_id=source_id,
                url=raw.url[:1000],  # column is String(1000) in current schema
                url_hash=_hash_text(raw.url) or "",
                title=title,  # column is String(1000)
                summary=full_body,
                # The ``body`` column is the persisted intro/full body for
                # crawlers that hand us the whole article up-front (RSS,
                # cninfo disclosures, Reddit selftext, …). We seed
                # ``full_content`` from the same source so a user who
                # clicks "load full text" sees an instant render rather
                # than waiting for the lazy Jina Reader fetch.
                body=full_body,
                full_content=full_body if _looks_full_article(full_body, source=raw.source) else None,
                content_hash=_simhash_text(full_body),
                author=raw.author,
                language=language,
                market=raw.market or "cn_a",
                published_at=_clamp_future_published_at(raw.published_at, source=raw.source),
                # ``category`` doubles as a free-form tag for source-specific
                # taxonomy (e.g. cninfo's filing category).
                category=_derive_category(raw),
                engagement=_safe_json({
                    **(raw.engagement or {}),
                    "extra": raw.extra or {},
                }),
            )
            self.db.add(article)
            # Flush so the article.id is available for the symbol rows
            # below. We do NOT commit — caller batches.
            self.db.flush()

            # 3) Symbol extraction.
            self._attach_symbols(article, raw)

            return article
        except SQLAlchemyError as exc:
            logger.warning("normalize: SQL error for url=%s: %s", raw.url, exc)
            self.db.rollback()
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("normalize: unexpected error for url=%s: %s", raw.url, exc)
            with contextlib.suppress(Exception):
                self.db.rollback()
            return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _attach_symbols(self, article: NewsArticle, raw: RawArticle) -> None:
        # For cninfo the disclosure carries an explicit ``stock_code`` —
        # prefer that over the text extractor.
        explicit_codes: list[tuple[str, str, float]] = []
        if raw.source == "cninfo":
            stock_code = (raw.extra or {}).get("stock_code")
            if stock_code:
                explicit_codes.append((_format_a_code(stock_code), "cn_a", 1.0))

        body_text = raw.body or _strip_html_to_text(raw.body_html) or ""
        extracted = self.symbol_extractor.extract(raw.title, body_text)

        candidates = explicit_codes + extracted
        if not candidates:
            return

        # Bulk-resolve display names from etf_info so each symbol row can
        # cache its human-readable label at ingestion time.
        candidate_codes = [sym for sym, _, _ in candidates]
        etf_rows = self.db.execute(
            select(ETFInfo.code, ETFInfo.name, ETFInfo.name_zh).where(
                ETFInfo.code.in_(candidate_codes)
            )
        ).all()
        etf_by_code = {row.code: row for row in etf_rows}

        seen: set[str] = set()
        for sym, _market, conf in candidates:
            if not sym or sym in seen:
                continue
            seen.add(sym)
            # Truncate to schema column size (String(20) in current schema).
            sym = sym[:20]
            etf = etf_by_code.get(sym)
            self.db.add(
                NewsArticleSymbol(
                    article_id=article.id,
                    symbol=sym,
                    name=etf.name if etf else None,
                    name_zh=etf.name_zh if etf else None,
                    match_type=_match_type_for(raw, conf),
                    confidence=int(round(_clamp(conf, 0.0, 1.0) * 100)),
                )
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
# 块级元素边界 → 段落换行（2026-08-01 huxiu 段落粘连根治，与
# rss_common._strip_html 同一规则）：剥标签前先把块级边界转成 \n\n
#（<br> 为段内单换行）。
_BLOCK_BOUNDARY_RE = re.compile(
    r"</(?:p|div|li|h[1-6]|blockquote|tr|section|article)\s*>",
    re.IGNORECASE,
)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_INLINE_WS_RE = re.compile(r"[ \t]+")
_EXCESS_NL_RE = re.compile(r"\n{3,}")


def _strip_html_to_text(value: str | None) -> str | None:
    """Best-effort HTML → text, preserving block-level breaks as ``\\n\\n``."""
    if not value:
        return None
    marked = _BR_RE.sub("\n", value)
    marked = _BLOCK_BOUNDARY_RE.sub("\n\n", marked)
    text = _HTML_TAG_RE.sub(" ", marked)
    # 行内空白折叠但保留段落换行；3+ 连续换行收敛为恰好 \n\n
    lines = [_INLINE_WS_RE.sub(" ", line).strip() for line in text.split("\n")]
    text = _EXCESS_NL_RE.sub("\n\n", "\n".join(lines)).strip()
    if not text:
        return None
    return text[:8000]


# Threshold below which we assume a body is just an excerpt (RSS blurb)
# rather than the full article. We never seed ``full_content`` from a
# blurb — the lazy Jina fetch has to do that work. Above ~400 chars the
# article is likely complete and we can short-circuit.
_FULL_BODY_MIN_CHARS = 400

# 2026-07-26: sources where the API already returns the complete article
# body. Their content should never be re-fetched via HTTP because their
# article pages are SPAs (trafilatura would extract nav/ads instead of
# the article text). For these sources, even short bodies count as
# "full" — 快讯 / flash headlines are naturally short and the API text
# is already the whole thing.
_SOURCES_WITH_API_FULL_CONTENT: frozenset[str] = frozenset({
    "wallstreetcn",  # 华尔街见闻 7×24 快讯 — SPA page, API has full text
    # 2026-07-29: 财联社电报 — the telegraph API ``content`` field IS the
    # complete flash (typically 30-300 chars); cls.cn detail pages are
    # Next.js SPAs so an HTTP re-fetch adds nothing but risk. Fixes ~40%
    # of cls rows sitting at full_content=NULL with endless refetch.
    "cls",
})


def _looks_full_article(value: str | None, source: str | None = None) -> bool:
    """Heuristic: is this body likely the full article (not just a teaser)?"""
    if not value:
        return False
    if source and source in _SOURCES_WITH_API_FULL_CONTENT:
        return True
    return len(value) >= _FULL_BODY_MIN_CHARS


def _format_a_code(value: str) -> str:
    """Map a cninfo ``secCode`` (e.g. ``"600519"``) to ``"600519.SH"``."""
    code = (value or "").strip().upper()
    if not code:
        return ""
    if code.endswith((".SH", ".SZ", ".BJ")):
        return code
    if len(code) == 6 and code.isdigit():
        first = code[0]
        if first in ("6", "9", "2"):
            return f"{code}.SH"
        if first in ("0", "3"):
            return f"{code}.SZ"
        if first in ("4", "8"):
            return f"{code}.BJ"
    return code


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _derive_category(raw: RawArticle) -> str | None:
    """Pick a coarse ``category`` for the article.

    For cninfo the filing category lives in ``raw.extra["category"]``.
    For everything else we leave it ``None`` — the LLM enrichment
    (Agent E) can fill it in later.
    """
    if not raw.extra:
        return None
    cat = raw.extra.get("category")
    return str(cat)[:100] if cat else None


def _match_type_for(raw: RawArticle, confidence: float) -> str:
    """Map an extraction confidence to a string ``match_type``.

    The downstream LLM pass (Agent E) can use this to weight extractions.
    """
    if raw.source == "cninfo" and (raw.extra or {}).get("stock_code"):
        return "filing_metadata"
    if confidence >= 0.95:
        return "code"
    if confidence >= 0.85:
        return "title"
    if confidence >= 0.70:
        return "alias"
    if confidence >= 0.60:
        return "cashtag"
    return "body"
