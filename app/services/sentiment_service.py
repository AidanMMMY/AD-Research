"""AI sentiment analysis service.

Ingests news articles from Finnhub and GDELT, classifies sentiment
using LLM (or pre-computed scores from GDELT), and stores results.

Finnhub free tier: 60 req/min, company news endpoint.
GDELT: completely free, unlimited, pre-computed "tone" scores.
"""

import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.data.providers.finnhub_provider import FinnhubProvider
from app.models.etf import ETFInfo
from app.models.research import SentimentData
from app.services.llm import DeepSeekProvider, LLMService

logger = logging.getLogger(__name__)


class SentimentService:
    """Multi-source sentiment analysis service."""

    def __init__(self, db: Session) -> None:
        self.db = db
        provider = DeepSeekProvider()
        self.llm = LLMService(provider)
        self.finnhub = FinnhubProvider()

    # ------------------------------------------------------------------
    # Finnhub News Ingestion
    # ------------------------------------------------------------------

    def ingest_finnhub_news(
        self, instrument_code: str, lookback_days: int = 3
    ) -> int:
        """Fetch and classify news articles for a single instrument.

        Returns count of new articles ingested.
        """
        to_date = date.today()
        from_date = to_date - timedelta(days=lookback_days)

        try:
            articles = self.finnhub.fetch_company_news(
                instrument_code, from_date, to_date
            )
        except Exception as exc:
            logger.warning("Finnhub news fetch failed for %s: %s", instrument_code, exc)
            return 0

        count = 0
        for article in articles[:20]:  # Limit per run to manage LLM costs
            # Skip if already exists
            existing = (
                self.db.query(SentimentData)
                .filter(SentimentData.instrument_code == instrument_code)
                .filter(SentimentData.url == article.get("url", ""))
                .filter(SentimentData.source == "finnhub_news")
                .first()
            )
            if existing:
                continue

            headline = article.get("headline", "")
            summary = article.get("summary", "")

            # Classify sentiment via LLM
            sentiment = self._classify_sentiment(headline, summary)

            record = SentimentData(
                instrument_code=instrument_code,
                source="finnhub_news",
                title=headline,
                content=summary,
                url=article.get("url", ""),
                sentiment_score=sentiment.get("score", 0),
                sentiment_label=sentiment.get("label", "neutral"),
                confidence=sentiment.get("confidence", 0.5),
                published_at=self._parse_datetime(article.get("datetime")),
            )
            self.db.add(record)
            count += 1

        if count:
            self.db.commit()
            logger.info("Ingested %d Finnhub news for %s", count, instrument_code)

        return count

    def ingest_finnhub_news_batch(
        self, instrument_codes: list[str], lookback_days: int = 3
    ) -> int:
        """Ingest news for multiple instruments. Rate-limited for free tier."""
        total = 0
        for code in instrument_codes[:10]:  # Limit to 10 instruments per batch
            total += self.ingest_finnhub_news(code, lookback_days)
        return total

    # ------------------------------------------------------------------
    # Sentiment Classification
    # ------------------------------------------------------------------

    def _classify_sentiment(
        self, headline: str, summary: str
    ) -> dict[str, Any]:
        """Classify sentiment of a news article using LLM."""
        prompt = f"""标题: {headline}

摘要: {summary}

请分类这篇新闻对相关股票的情绪影响。只返回JSON：
{{"label": "positive|negative|neutral", "score": -1.0到1.0之间, "confidence": 0.0到1.0之间}}
"""
        try:
            result = self.llm.complete_with_cache(
                prompt=prompt,
                system=self.llm.SENTIMENT_SYSTEM,
                max_tokens=100,
                temperature=0.1,
            )
            return self._parse_json_response(result)
        except Exception as exc:
            logger.warning("Sentiment classification failed: %s", exc)
            return {"label": "neutral", "score": 0.0, "confidence": 0.3}

    # ------------------------------------------------------------------
    # Aggregate Sentiment
    # ------------------------------------------------------------------

    def get_aggregate_sentiment(
        self, instrument_code: str, lookback_days: int = 7
    ) -> dict[str, Any] | None:
        """Compute aggregate sentiment for an instrument."""
        since = datetime.now() - timedelta(days=lookback_days)

        records = (
            self.db.query(SentimentData)
            .filter(SentimentData.instrument_code == instrument_code)
            .filter(SentimentData.ingested_at >= since)
            .all()
        )

        if not records:
            return None

        scores = [float(r.sentiment_score) for r in records if r.sentiment_score is not None]
        if not scores:
            return None

        avg_score = sum(scores) / len(scores)
        positive = sum(1 for s in scores if s > 0.1)
        negative = sum(1 for s in scores if s < -0.1)
        neutral = len(scores) - positive - negative

        if avg_score > 0.15:
            label = "positive"
        elif avg_score < -0.15:
            label = "negative"
        else:
            label = "neutral"

        return {
            "instrument_code": instrument_code,
            "avg_score": round(avg_score, 4),
            "label": label,
            "positive_count": positive,
            "negative_count": negative,
            "neutral_count": neutral,
            "total_articles": len(scores),
            "period_days": lookback_days,
        }

    def get_market_sentiment(
        self, instrument_codes: list[str], lookback_days: int = 7
    ) -> list[dict[str, Any]]:
        """Get aggregate sentiment for multiple instruments."""
        results = []
        for code in instrument_codes:
            agg = self.get_aggregate_sentiment(code, lookback_days)
            if agg:
                results.append(agg)
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        if "{" in text:
            try:
                return json.loads(text[text.index("{"): text.rindex("}") + 1])
            except json.JSONDecodeError:
                pass
        return {}

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            if isinstance(value, (int, float)):
                return datetime.fromtimestamp(value)
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
