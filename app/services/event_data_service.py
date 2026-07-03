"""Event data service.

A single source-of-truth layer that aggregates *events* (currently news
sentiment) for a given instrument over a lookback window. Strategies query
this service instead of hitting the raw tables directly.

Sentiment sources, in priority order:

1. ``sentiment_data`` (LLM pipeline output, ``instrument_code`` keyed,
   score range ``-1.0 .. 1.0``). This is the richest signal when present.
2. ``news_article`` joined to ``news_article_symbol`` (``symbol`` keyed).
   Uses ``news_article.sentiment_score`` (``-100 .. 100``) when populated,
   otherwise falls back to a lightweight Chinese/English keyword count.

All per-article scores are normalised to ``0.0 .. 1.0`` (0 = maximally
bearish, 0.5 = neutral, 1 = maximally bullish) before aggregation so the
strategy layer sees one consistent scale.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.models.research import SentimentData
from app.services.news._model_loader import NewsArticle, NewsArticleSymbol
from app.services.symbol_mapper import internal_code

# Keyword lexicon for the no-LLM text fallback. Deliberately small and
# high-precision; this only runs when no numeric sentiment is available.
_POSITIVE_WORDS = (
    "利好", "增长", "上涨", "大涨", "涨停", "盈利", "超预期", "回购", "增持",
    "beat", "surge", "soar", "record", "upgrade", "bullish", "rally", "gain",
)
_NEGATIVE_WORDS = (
    "利空", "下跌", "大跌", "跌停", "亏损", "不及预期", "减持", "退市", "违规",
    "miss", "plunge", "slump", "downgrade", "bearish", "lawsuit", "fraud", "loss",
)

# Neutral band around 0.5 used to bucket a normalised score.
_NEUTRAL_LOW = 0.45
_NEUTRAL_HIGH = 0.55


def _bucket(score: float) -> str:
    """Classify a normalised (0..1) score into pos / neg / neutral."""
    if score > _NEUTRAL_HIGH:
        return "positive"
    if score < _NEUTRAL_LOW:
        return "negative"
    return "neutral"


def _text_sentiment(*parts: str | None) -> float | None:
    """Keyword-count fallback. Returns a 0..1 score or ``None`` if no hits."""
    haystack = " ".join(p for p in parts if p).lower()
    if not haystack:
        return None
    pos = sum(1 for w in _POSITIVE_WORDS if w.lower() in haystack)
    neg = sum(1 for w in _NEGATIVE_WORDS if w.lower() in haystack)
    if pos == 0 and neg == 0:
        return None
    # Map the pos/neg balance onto 0..1.
    return (pos) / (pos + neg)


class EventDataService:
    """Aggregates event signals for strategies over a lookback window."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_news_sentiment(
        self,
        code: str,
        trade_date: date,
        lookback_days: int = 5,
    ) -> dict:
        """Aggregate news sentiment for ``code`` over the lookback window.

        Args:
            code: Instrument symbol, internal (``AAPL.US``) or plain
                (``AAPL``); it is normalised via
                :func:`app.services.symbol_mapper.internal_code`.
            trade_date: The as-of date; the window is
                ``[trade_date - lookback_days, trade_date]`` inclusive.
            lookback_days: Number of calendar days to look back.

        Returns:
            ``{"avg_sentiment": float 0..1, "count": int,
               "positive": int, "negative": int, "neutral": int}``.
            ``avg_sentiment`` defaults to ``0.5`` (neutral) when no
            events are found.
        """
        symbol = internal_code(code)
        start = datetime.combine(trade_date - timedelta(days=lookback_days), time.min)
        end = datetime.combine(trade_date, time.max)

        scores: list[float] = []

        # --- Source 1: sentiment_data (LLM pipeline, -1..1) --------------
        rows = (
            self.db.query(SentimentData)
            .filter(SentimentData.instrument_code == symbol)
            .filter(SentimentData.sentiment_score.isnot(None))
            .filter(SentimentData.published_at >= start)
            .filter(SentimentData.published_at <= end)
            .all()
        )
        for row in rows:
            try:
                raw = float(row.sentiment_score)
            except (TypeError, ValueError):
                continue
            # -1..1 -> 0..1
            scores.append(max(0.0, min(1.0, (raw + 1.0) / 2.0)))

        # --- Source 2: news_article via news_article_symbol -------------
        articles = (
            self.db.query(NewsArticle)
            .join(NewsArticleSymbol, NewsArticleSymbol.article_id == NewsArticle.id)
            .filter(NewsArticleSymbol.symbol == symbol)
            .filter(NewsArticle.published_at >= start)
            .filter(NewsArticle.published_at <= end)
            .all()
        )
        for art in articles:
            if art.sentiment_score is not None:
                # -100..100 -> 0..1
                scores.append(max(0.0, min(1.0, (float(art.sentiment_score) + 100.0) / 200.0)))
            else:
                fallback = _text_sentiment(art.title, art.summary)
                if fallback is not None:
                    scores.append(fallback)

        count = len(scores)
        if count == 0:
            return {
                "avg_sentiment": 0.5,
                "count": 0,
                "positive": 0,
                "negative": 0,
                "neutral": 0,
            }

        avg = sum(scores) / count
        buckets = {"positive": 0, "negative": 0, "neutral": 0}
        for s in scores:
            buckets[_bucket(s)] += 1

        return {
            "avg_sentiment": avg,
            "count": count,
            "positive": buckets["positive"],
            "negative": buckets["negative"],
            "neutral": buckets["neutral"],
        }
