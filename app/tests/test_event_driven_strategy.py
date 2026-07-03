"""Tests for the event-driven strategy, symbol mapper, and event data service."""

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from app.models.research import SentimentData
from app.services.event_data_service import EventDataService
from app.services.news._model_loader import NewsArticle, NewsArticleSymbol
from app.services.symbol_mapper import internal_code
from app.strategies.event import EventDrivenStrategy


# ---------------------------------------------------------------------------
# Symbol mapper
# ---------------------------------------------------------------------------
class TestSymbolMapper:
    def test_us_ticker(self):
        assert internal_code("AAPL") == "AAPL.US"
        assert internal_code("tsla") == "TSLA.US"

    def test_a_share_shanghai(self):
        assert internal_code("600519") == "600519.SH"

    def test_a_share_shenzhen(self):
        assert internal_code("000001") == "000001.SZ"
        assert internal_code("300750") == "300750.SZ"

    def test_a_share_beijing(self):
        assert internal_code("430047") == "430047.BJ"

    def test_hong_kong(self):
        assert internal_code("00700") == "00700.HK"
        assert internal_code("0700") == "00700.HK"

    def test_already_internal(self):
        assert internal_code("AAPL.US") == "AAPL.US"
        assert internal_code("600519.SH") == "600519.SH"

    def test_dotted_us_ticker(self):
        assert internal_code("BRK.B") == "BRK.B.US"

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            internal_code("")


# ---------------------------------------------------------------------------
# Event data service
# ---------------------------------------------------------------------------
def _add_article(db, symbol, published_at, *, title="", summary="", score=None):
    art = NewsArticle(
        source="test",
        source_id=f"id-{title}-{published_at.isoformat()}",
        url=f"http://example.com/{title}-{published_at.isoformat()}",
        url_hash=f"hash-{title}-{published_at.isoformat()}"[:32],
        title=title or "headline",
        summary=summary,
        published_at=published_at,
        sentiment_score=score,
    )
    db.add(art)
    db.flush()
    db.add(NewsArticleSymbol(article_id=art.id, symbol=symbol, match_type="title"))
    db.commit()
    return art


class TestEventDataService:
    def test_no_events_returns_neutral(self, db_session):
        svc = EventDataService(db_session)
        result = svc.get_news_sentiment("AAPL", date(2026, 7, 3))
        assert result == {
            "avg_sentiment": 0.5,
            "count": 0,
            "positive": 0,
            "negative": 0,
            "neutral": 0,
        }

    def test_numeric_sentiment_score(self, db_session):
        today = date(2026, 7, 3)
        ts = datetime(2026, 7, 2, 10, 0, 0)
        # +80 -> 0.9 normalised (bullish)
        _add_article(db_session, "AAPL.US", ts, title="a", score=80)
        _add_article(db_session, "AAPL.US", ts, title="b", score=60)
        result = EventDataService(db_session).get_news_sentiment("AAPL", today)
        assert result["count"] == 2
        assert result["avg_sentiment"] == pytest.approx((0.9 + 0.8) / 2)
        assert result["positive"] == 2

    def test_text_fallback(self, db_session):
        today = date(2026, 7, 3)
        ts = datetime(2026, 7, 2, 10, 0, 0)
        _add_article(db_session, "600519.SH", ts, title="公司发布利好消息，业绩大涨")
        _add_article(db_session, "600519.SH", ts, title="重大利空，股价大跌")
        result = EventDataService(db_session).get_news_sentiment("600519", today)
        assert result["count"] == 2
        assert result["positive"] == 1
        assert result["negative"] == 1

    def test_lookback_window_excludes_old(self, db_session):
        today = date(2026, 7, 3)
        old = datetime(2026, 6, 1, 10, 0, 0)
        _add_article(db_session, "AAPL.US", old, title="old", score=90)
        result = EventDataService(db_session).get_news_sentiment(
            "AAPL", today, lookback_days=5
        )
        assert result["count"] == 0

    def test_sentiment_data_source(self, db_session):
        today = date(2026, 7, 3)
        ts = datetime(2026, 7, 2, 10, 0, 0)
        db_session.add(
            SentimentData(
                instrument_code="AAPL.US",
                source="llm_pipeline",
                sentiment_score=0.8,  # -1..1 -> 0.9
                sentiment_label="positive",
                published_at=ts,
            )
        )
        db_session.commit()
        result = EventDataService(db_session).get_news_sentiment("AAPL", today)
        assert result["count"] == 1
        assert result["avg_sentiment"] == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------
def _bars(code, as_of, n=3):
    dates = [as_of - timedelta(days=i) for i in range(n)][::-1]
    return pd.DataFrame(
        {
            "trade_date": [pd.Timestamp(d) for d in dates],
            "etf_code": [code] * n,
            "close": [100.0] * n,
        }
    )


class TestEventDrivenStrategy:
    def test_buy_on_positive_news(self, db_session):
        today = date(2026, 7, 3)
        ts = datetime(2026, 7, 2, 10, 0, 0)
        for i in range(3):
            _add_article(db_session, "AAPL.US", ts, title=f"pos-{i}", score=80)
        strat = EventDrivenStrategy({"event_types": "news", "lookback_days": 5}, db=db_session)
        result = strat.generate(_bars("AAPL.US", today))
        assert result.signal_type == "BUY"
        assert result.strength > 60

    def test_sell_on_negative_news(self, db_session):
        today = date(2026, 7, 3)
        ts = datetime(2026, 7, 2, 10, 0, 0)
        for i in range(3):
            _add_article(db_session, "AAPL.US", ts, title=f"neg-{i}", score=-80)
        strat = EventDrivenStrategy({"event_types": "news", "lookback_days": 5}, db=db_session)
        result = strat.generate(_bars("AAPL.US", today))
        assert result.signal_type == "SELL"
        assert result.strength > 60

    def test_hold_on_insufficient_count(self, db_session):
        today = date(2026, 7, 3)
        ts = datetime(2026, 7, 2, 10, 0, 0)
        _add_article(db_session, "AAPL.US", ts, title="pos", score=80)
        strat = EventDrivenStrategy({"event_types": "news", "lookback_days": 5}, db=db_session)
        result = strat.generate(_bars("AAPL.US", today))
        assert result.signal_type == "HOLD"

    def test_hold_without_db(self):
        strat = EventDrivenStrategy({"event_types": "news"})
        result = strat.generate(_bars("AAPL.US", date(2026, 7, 3)))
        assert result.signal_type == "HOLD"

    def test_generate_series(self, db_session):
        today = date(2026, 7, 3)
        ts = datetime(2026, 7, 2, 10, 0, 0)
        for i in range(3):
            _add_article(db_session, "AAPL.US", ts, title=f"pos-{i}", score=80)
        strat = EventDrivenStrategy({"event_types": "news", "lookback_days": 5}, db=db_session)
        series = strat.generate_series(_bars("AAPL.US", today, n=3))
        assert len(series) == 3
        # Last bar (today) sees the positive news -> BUY (1).
        assert series.iloc[-1] == 1

    def test_description_not_placeholder(self):
        assert "占位" not in EventDrivenStrategy.description
