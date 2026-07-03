"""Unit tests for the news module (Agent B).

Coverage:
  - SymbolExtractor: A-share name / code / US cashtag extraction.
  - NewsNormalizer: dedup on (source, source_id) plus happy path.
  - API list / detail endpoints (smoke tests with an in-memory SQLite
    DB and FastAPI's TestClient, JWT mocked via the existing
    ``get_current_user`` dep).
  - Source crawler XML/JSON parsing (without hitting the network).

The tests use the shared ``db_session`` fixture from
``app/tests/conftest.py`` so the schema lives in a fresh
``sqlite:///:memory:`` engine per test.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.services.news._model_loader import NewsArticle, NewsArticleSymbol
from app.services.news.crawler.types import RawArticle
from app.services.news.normalizer import NewsNormalizer
from app.services.news.sources.cninfo import CninfoCrawler
from app.services.news.sources.sina import SinaCrawler
from app.services.news.sources.xinhua import XinhuaCrawler
from app.services.news.symbol_extractor import SymbolExtractor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def news_db():
    """Fresh in-memory SQLite with only the news tables created.

    Uses :class:`StaticPool` so the single connection is shared across
    threads — FastAPI's TestClient runs dependency callbacks in a
    worker thread, and a vanilla ``:memory:`` engine throws a
    ``ProgrammingError`` on the second thread.
    """
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _make_etf(db, *, code: str, name: str, market: str = "A股"):
    """Insert a single ETFInfo row used as the symbol-extractor lookup."""
    from app.models.etf import ETFInfo

    row = ETFInfo(code=code, name=name, market=market, instrument_type="ETF", status="active")
    db.add(row)
    db.commit()
    return row


# ---------------------------------------------------------------------------
# Symbol extractor
# ---------------------------------------------------------------------------

class TestSymbolExtractor:
    def test_extract_a_share_explicit_code_with_suffix(self, news_db):
        syms = SymbolExtractor(news_db).extract(
            "贵州茅台 600519.SH 发布三季报", None
        )
        codes = {s for s, _, _ in syms}
        assert "600519.SH" in codes

    def test_extract_a_share_bare_code_infers_exchange(self, news_db):
        syms = SymbolExtractor(news_db).extract("600519 大涨 5%", None)
        codes = {s for s, _, _ in syms}
        assert "600519.SH" in codes

    def test_extract_a_share_bare_sz_code(self, news_db):
        syms = SymbolExtractor(news_db).extract("000001 涨幅居前", None)
        codes = {s for s, _, _ in syms}
        assert "000001.SZ" in codes

    def test_extract_a_share_by_name(self, news_db):
        _make_etf(news_db, code="510300.SH", name="沪深300ETF", market="A股")
        syms = SymbolExtractor(news_db).extract("沪深300ETF 持续上涨", None)
        codes = {s for s, _, _ in syms}
        assert "510300.SH" in codes

    def test_extract_a_share_by_abbreviation(self, news_db):
        _make_etf(news_db, code="510500.SH", name="中证500ETF", market="A股")
        syms = SymbolExtractor(news_db).extract("中证500 走势", None)
        codes = {s for s, _, _ in syms}
        assert "510500.SH" in codes

    def test_extract_us_cashtag(self, news_db):
        syms = SymbolExtractor(news_db).extract("Apple $AAPL 创新高", None)
        codes = {s for s, _, _ in syms}
        assert "AAPL.US" in codes

    def test_extract_empty_text_returns_empty(self, news_db):
        syms = SymbolExtractor(news_db).extract("", None)
        assert syms == []

    def test_extract_no_match_returns_empty(self, news_db):
        syms = SymbolExtractor(news_db).extract("随便说点什么", None)
        assert syms == []

    def test_invalid_6_digit_code_skipped(self, news_db):
        # 1xxxxx is not an A-share prefix; should be ignored.
        syms = SymbolExtractor(news_db).extract("123456 没关系", None)
        codes = {s for s, _, _ in syms}
        assert not any(c.startswith("123456") for c in codes)

    def test_cache_invalidation(self, news_db):
        extractor = SymbolExtractor(news_db)
        # Empty DB -> nothing.
        assert extractor.extract("沪深300", None) == []
        # Add the ETF, then invalidate to force a cache rebuild.
        _make_etf(news_db, code="510300.SH", name="沪深300ETF", market="A股")
        extractor.invalidate_cache()
        syms = extractor.extract("沪深300 上涨", None)
        codes = {s for s, _, _ in syms}
        assert "510300.SH" in codes

    def test_results_sorted_by_confidence_desc(self, news_db):
        syms = SymbolExtractor(news_db).extract(
            "600519.SH 茅台 $TSLA", None
        )
        # Confidence must be monotonically non-increasing.
        confs = [c for _, _, c in syms]
        assert confs == sorted(confs, reverse=True)


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------

def _raw(*, source="xinhua_rss", source_id="abc", url="https://x/a",
         title="测试标题", body=None, body_html=None, market="cn_a",
         language="zh", published_at=None):
    return RawArticle(
        source=source,
        source_id=source_id,
        url=url,
        title=title,
        body=body,
        body_html=body_html,
        author=None,
        published_at=published_at or datetime(2026, 7, 1, tzinfo=timezone.utc),
        language=language,
        market=market,
    )


class TestNewsNormalizer:
    def test_normalize_happy_path_inserts_row(self, news_db):
        normalizer = NewsNormalizer(news_db)
        raw = _raw(title="600519.SH 贵州茅台 涨停")
        article = normalizer.normalize(raw)
        assert article is not None
        news_db.commit()
        assert article.id is not None
        assert article.source == "xinhua_rss"
        # Should have at least one linked symbol.
        sym_codes = [s.symbol for s in article.symbols]
        assert "600519.SH" in sym_codes

    def test_normalize_caches_symbol_names_from_etf_info(self, news_db):
        _make_etf(news_db, code="510300.SH", name="沪深300ETF", market="A股")
        # Set English display name separately because _make_etf doesn't expose it.
        from app.models.etf import ETFInfo
        etf = news_db.get(ETFInfo, "510300.SH")
        etf.name_zh = "CSI 300 ETF"
        news_db.commit()

        normalizer = NewsNormalizer(news_db)
        raw = _raw(title="沪深300ETF 持续上涨")
        article = normalizer.normalize(raw)
        assert article is not None
        news_db.commit()

        sym = next(s for s in article.symbols if s.symbol == "510300.SH")
        assert sym.name == "沪深300ETF"
        assert sym.name_zh == "CSI 300 ETF"

    def test_normalize_dedup_skips_duplicate(self, news_db):
        normalizer = NewsNormalizer(news_db)
        raw = _raw(source_id="dup-1")
        first = normalizer.normalize(raw)
        news_db.commit()
        assert first is not None
        # Second time, same source+source_id -> None
        again = normalizer.normalize(raw)
        assert again is None

    def test_normalize_html_summary_stripped(self, news_db):
        normalizer = NewsNormalizer(news_db)
        raw = _raw(body=None, body_html="<p>Hello <b>world</b></p>")
        article = normalizer.normalize(raw)
        assert article is not None
        assert article.summary and "<" not in article.summary
        news_db.commit()

    def test_normalize_cninfo_uses_explicit_stock_code(self, news_db):
        normalizer = NewsNormalizer(news_db)
        raw = _raw(
            source="cninfo",
            source_id="ann-1",
            title="<em>公司</em>公告",
            extra={"stock_code": "600519"},
        ) if False else RawArticle(  # RawArticle doesn't accept extra via kwargs
            source="cninfo",
            source_id="ann-1",
            url="http://static.cninfo.com.cn/finalpage/2026-07-01/123.PDF",
            title="公司公告",
            published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            market="cn_a",
            language="zh",
            extra={"stock_code": "600519", "stock_name": "贵州茅台"},
        )
        article = normalizer.normalize(raw)
        assert article is not None
        sym_codes = [s.symbol for s in article.symbols]
        assert "600519.SH" in sym_codes
        # Filing_metadata wins over text match for the source's own code.
        match_types = {s.match_type for s in article.symbols if s.symbol == "600519.SH"}
        assert "filing_metadata" in match_types
        news_db.commit()

    def test_normalize_missing_title_returns_none(self, news_db):
        normalizer = NewsNormalizer(news_db)
        raw = RawArticle(
            source="xinhua_rss",
            source_id="x1",
            url="http://x",
            title="",
            published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        assert normalizer.normalize(raw) is None

    def test_normalize_missing_url_returns_none(self, news_db):
        normalizer = NewsNormalizer(news_db)
        raw = RawArticle(
            source="xinhua_rss",
            source_id="x2",
            url="",
            title="title",
            published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        assert normalizer.normalize(raw) is None

    def test_engagement_round_trips_as_json(self, news_db):
        normalizer = NewsNormalizer(news_db)
        raw = _raw()
        raw.engagement = {"likes": 5, "comments": 2}
        article = normalizer.normalize(raw)
        assert article is not None
        assert article.engagement is not None
        # sqlite stores JSON as TEXT; ensure content survives round-trip.
        assert article.engagement.get("likes") == 5
        news_db.commit()


# ---------------------------------------------------------------------------
# API smoke tests
# ---------------------------------------------------------------------------

class _FakeUser:
    """A stand-in for the JWT-auth user."""
    username = "tester"
    role = "user"


@pytest.fixture
def api_client(news_db):
    """Build a TestClient with the get_db dep overridden to use ``news_db``."""
    from fastapi import FastAPI
    from app.api.v1 import news as news_module

    def _override_db():
        try:
            yield news_db
        finally:
            pass

    def _override_user():
        return _FakeUser()

    # Build a minimal FastAPI app and mount the news router. Mounting
    # (rather than overriding on the router itself) gives us a real
    # ``app.dependency_overrides`` mapping.
    test_app = FastAPI()
    test_app.include_router(news_module.router, prefix="/api/v1/news")
    test_app.dependency_overrides[news_module.get_db] = _override_db
    test_app.dependency_overrides[news_module.get_current_user] = _override_user
    with TestClient(test_app) as client:
        yield client
    test_app.dependency_overrides.clear()


def _seed_articles(news_db, n: int = 3):
    """Insert a handful of articles so list/detail have something to return."""
    now = datetime.now(tz=timezone.utc)
    rows = []
    for i in range(n):
        a = NewsArticle(
            source="xinhua_rss" if i % 2 == 0 else "sina_finance",
            source_id=f"seed-{i}",
            url=f"https://example.com/{i}",
            url_hash=f"hash-{i}",
            title=f"Article {i}",
            summary=f"Body {i}",
            language="zh",
            market="cn_a",
            published_at=now - timedelta(hours=i),
        )
        news_db.add(a)
        rows.append(a)
    news_db.commit()
    for r in rows:
        news_db.refresh(r)
    return rows


class TestNewsApi:
    def test_list_returns_seeded(self, api_client, news_db):
        seeded = _seed_articles(news_db, n=3)
        resp = api_client.get("/api/v1/news", params={"page": 1, "page_size": 10})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total"] == 3
        assert len(payload["items"]) == 3
        # Newest first.
        assert payload["items"][0]["title"] == "Article 0"

    def test_list_filter_by_market(self, api_client, news_db):
        _seed_articles(news_db, n=2)
        # Add a US article.
        news_db.add(
            NewsArticle(
                source="yahoo_finance",
                source_id="us-1",
                url="https://example.com/us",
                url_hash="hash-us-1",
                title="US Article",
                language="en",
                market="us",
                published_at=datetime.now(tz=timezone.utc),
            )
        )
        news_db.commit()
        resp = api_client.get("/api/v1/news", params={"market": "us"})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total"] == 1
        assert payload["items"][0]["title"] == "US Article"

    def test_list_filter_by_source(self, api_client, news_db):
        _seed_articles(news_db, n=3)
        resp = api_client.get("/api/v1/news", params={"source": "sina_finance"})
        assert resp.status_code == 200
        payload = resp.json()
        # Half of the 3 seeded are sina_finance.
        assert payload["total"] == 1
        assert payload["items"][0]["source"] == "sina_finance"

    def test_list_filter_by_importance_min(self, api_client, news_db):
        _seed_articles(news_db, n=2)
        # Update one article to importance=4.
        articles = news_db.query(NewsArticle).all()
        articles[0].importance = 4
        articles[1].importance = 2
        news_db.commit()
        resp = api_client.get("/api/v1/news", params={"importance_min": 4})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total"] == 1
        assert payload["items"][0]["title"] == articles[0].title
        assert payload["total_pages"] == 1

    def test_retail_sentiment_returns_aggregate(self, api_client, news_db):
        from app.models.etf import ETFInfo
        news_db.add(ETFInfo(code="510300.SH", name="沪深300ETF", market="A股", instrument_type="ETF", status="active"))
        now = datetime.now(tz=timezone.utc)
        article = NewsArticle(
            source="reddit",
            source_id="r-1",
            url="https://example.com/r1",
            url_hash="hash-r1",
            title="Bullish on 510300",
            language="en",
            market="cn_a",
            published_at=now,
            sentiment_score=75,
            sentiment_label="positive",
            importance=4,
            event_category="earnings",
        )
        news_db.add(article)
        news_db.commit()
        news_db.refresh(article)
        news_db.add(NewsArticleSymbol(article_id=article.id, symbol="510300.SH", match_type="code"))
        news_db.commit()

        resp = api_client.get("/api/v1/news/retail-sentiment/510300.SH")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["symbol"] == "510300.SH"
        assert payload["overall"] > 0
        assert payload["bull_bear_ratio"]["bull"] > 0
        assert payload["controversy"] >= 0
        assert payload["controversy"] <= 1
        assert isinstance(payload["main_themes"], list)
        assert payload["article_count"] == 1

    def test_retail_sentiment_404_when_no_data(self, api_client, news_db):
        resp = api_client.get("/api/v1/news/retail-sentiment/UNKNOWN.CODE")
        assert resp.status_code == 404

    def test_list_filter_by_symbol(self, api_client, news_db):
        seeded = _seed_articles(news_db, n=2)
        news_db.add(
            NewsArticleSymbol(
                article_id=seeded[0].id, symbol="600519.SH", match_type="code", confidence=95
            )
        )
        news_db.commit()
        resp = api_client.get("/api/v1/news", params={"symbol": "600519.SH"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_list_invalid_date_returns_400(self, api_client, news_db):
        resp = api_client.get("/api/v1/news", params={"from_date": "not-a-date"})
        assert resp.status_code == 400

    def test_get_article_returns_symbols(self, api_client, news_db):
        seeded = _seed_articles(news_db, n=1)
        news_db.add(
            NewsArticleSymbol(
                article_id=seeded[0].id, symbol="510300.SH", match_type="title", confidence=90
            )
        )
        news_db.commit()
        resp = api_client.get(f"/api/v1/news/{seeded[0].id}")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["title"] == "Article 0"
        symbol_codes = {s["symbol"] for s in payload["symbols"]}
        assert "510300.SH" in symbol_codes
        symbol = next(s for s in payload["symbols"] if s["symbol"] == "510300.SH")
        assert symbol["match_type"] == "title"
        assert "name" in symbol
        assert "name_zh" in symbol

    def test_get_article_404(self, api_client, news_db):
        resp = api_client.get("/api/v1/news/99999")
        assert resp.status_code == 404

    def test_stats_sources_aggregation(self, api_client, news_db):
        _seed_articles(news_db, n=4)  # 2 xinhua, 2 sina
        resp = api_client.get("/api/v1/news/stats/sources")
        assert resp.status_code == 200
        payload = resp.json()
        sources = {s["source"]: s for s in payload["sources"]}
        assert sources["xinhua_rss"]["total"] == 2
        assert sources["sina_finance"]["total"] == 2

    def test_health_returns_all_sources(self, api_client, news_db):
        # Seed a single recent article on cninfo to confirm aggregation.
        now = datetime.now(tz=timezone.utc)
        news_db.add(
            NewsArticle(
                source="cninfo",
                source_id="h-1",
                url="https://example.com/h1",
                url_hash="hash-h-1",
                title="cninfo article",
                language="zh",
                market="cn_a",
                published_at=now,
                fetched_at=now,
            )
        )
        news_db.commit()
        resp = api_client.get("/api/v1/news/health")
        assert resp.status_code == 200
        payload = resp.json()
        # All registered news sources must be returned, even when DB is empty.
        # Kept in sync with ``_NEWS_SOURCES`` in app/api/v1/news.py.
        source_ids = {s["source"] for s in payload["sources"]}
        assert source_ids == {
            "cninfo",
            "sina_finance",
            "wechat_zeping",
            "yahoo_finance",
            "cnbc",
            "sec_edgar",
            "reddit",
            "xueqiu",
            "coindesk",
            "cointelegraph",
        }
        cninfo_row = next(s for s in payload["sources"] if s["source"] == "cninfo")
        assert cninfo_row["total"] == 1
        assert cninfo_row["last_24h"] == 1
        assert cninfo_row["last_published_at"] is not None
        assert cninfo_row["job_id"] == "news_cninfo_10m"
        # Empty source still in list with 0/null.
        xueqiu_row = next(s for s in payload["sources"] if s["source"] == "xueqiu")
        assert xueqiu_row["total"] == 0
        assert xueqiu_row["last_published_at"] is None
        assert xueqiu_row["job_id"] == "news_xueqiu_5m"
        # WeChat source is wired up to its scheduler job id.
        wechat_row = next(
            s for s in payload["sources"] if s["source"] == "wechat_zeping"
        )
        assert wechat_row["job_id"] == "news_wechat_zeping_15m"
        assert wechat_row["total"] == 0
        # Scheduler introspection is included.
        assert "scheduler_running" in payload
        assert isinstance(payload["scheduler_jobs"], list)
        assert "as_of" in payload

    # ------------------------------------------------------------------
    # /news/watchlist — scoped to the current user's favorites
    # ------------------------------------------------------------------

    def _add_favorite(self, news_db, *, username: str, etf_code: str):
        from app.models.favorite import UserFavorite

        news_db.add(
            UserFavorite(
                id=f"{username}_{etf_code}",
                username=username,
                etf_code=etf_code,
            )
        )
        news_db.commit()

    def test_watchlist_returns_only_favorite_articles(self, api_client, news_db):
        seeded = _seed_articles(news_db, n=2)
        # Link first article to 510300.SH; second to 510500.SH.
        news_db.add(
            NewsArticleSymbol(
                article_id=seeded[0].id, symbol="510300.SH", match_type="code"
            )
        )
        news_db.add(
            NewsArticleSymbol(
                article_id=seeded[1].id, symbol="510500.SH", match_type="code"
            )
        )
        news_db.commit()
        # User only favorites 510300.SH.
        self._add_favorite(news_db, username="tester", etf_code="510300.SH")

        resp = api_client.get("/api/v1/news/watchlist")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total"] == 1
        assert payload["items"][0]["id"] == seeded[0].id
        symbol_codes = {s["symbol"] for s in payload["items"][0]["symbols"]}
        assert "510300.SH" in symbol_codes
        assert payload["watchlist"]["symbols"] == ["510300.SH"]
        assert payload["watchlist"]["symbols_with_news"] == 1
        assert payload["watchlist"]["total_articles"] == 1

    def test_watchlist_empty_for_user_with_no_favorites(self, api_client, news_db):
        _seed_articles(news_db, n=2)
        resp = api_client.get("/api/v1/news/watchlist")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["items"] == []
        assert payload["total"] == 0
        assert payload["watchlist"]["symbols"] == []
        assert payload["watchlist"]["symbols_with_news"] == 0

    def test_watchlist_includes_all_user_favorites(self, api_client, news_db):
        seeded = _seed_articles(news_db, n=3)
        news_db.add(NewsArticleSymbol(article_id=seeded[0].id, symbol="510300.SH"))
        news_db.add(NewsArticleSymbol(article_id=seeded[1].id, symbol="510500.SH"))
        news_db.add(NewsArticleSymbol(article_id=seeded[2].id, symbol="159915.SZ"))
        news_db.commit()
        self._add_favorite(news_db, username="tester", etf_code="510300.SH")
        self._add_favorite(news_db, username="tester", etf_code="510500.SH")
        # 159915.SZ is NOT favorited -> article excluded.

        resp = api_client.get("/api/v1/news/watchlist")
        assert resp.status_code == 200
        payload = resp.json()
        ids = {item["id"] for item in payload["items"]}
        assert ids == {seeded[0].id, seeded[1].id}
        assert set(payload["watchlist"]["symbols"]) == {"510300.SH", "510500.SH"}
        assert payload["watchlist"]["symbols_with_news"] == 2

    def test_watchlist_respects_market_filter(self, api_client, news_db):
        seeded = _seed_articles(news_db, n=1)
        news_db.add(NewsArticleSymbol(article_id=seeded[0].id, symbol="510300.SH"))
        # Add a US article linked to a US favorite.
        us_article = NewsArticle(
            source="yahoo_finance",
            source_id="us-1",
            url="https://example.com/us",
            url_hash="hash-us-1",
            title="US Article",
            language="en",
            market="us",
            published_at=datetime.now(tz=timezone.utc),
        )
        news_db.add(us_article)
        news_db.commit()
        news_db.refresh(us_article)
        news_db.add(NewsArticleSymbol(article_id=us_article.id, symbol="AAPL.US"))
        news_db.commit()
        self._add_favorite(news_db, username="tester", etf_code="510300.SH")
        self._add_favorite(news_db, username="tester", etf_code="AAPL.US")

        resp = api_client.get("/api/v1/news/watchlist", params={"market": "us"})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total"] == 1
        assert payload["items"][0]["title"] == "US Article"
        assert payload["watchlist"]["symbols_with_news"] == 1

    def test_watchlist_isolated_by_user(self, api_client, news_db):
        """Articles should match only the *current* user's favorites."""
        seeded = _seed_articles(news_db, n=1)
        news_db.add(NewsArticleSymbol(article_id=seeded[0].id, symbol="510300.SH"))
        news_db.commit()
        # Favorite belongs to a *different* user.
        self._add_favorite(news_db, username="someone-else", etf_code="510300.SH")

        resp = api_client.get("/api/v1/news/watchlist")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["items"] == []
        assert payload["total"] == 0
        assert payload["watchlist"]["symbols"] == []

    def test_watchlist_paginates(self, api_client, news_db):
        articles = _seed_articles(news_db, n=5)
        for a in articles:
            news_db.add(NewsArticleSymbol(article_id=a.id, symbol="510300.SH"))
        news_db.commit()
        self._add_favorite(news_db, username="tester", etf_code="510300.SH")

        resp = api_client.get(
            "/api/v1/news/watchlist", params={"page": 2, "page_size": 2}
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total"] == 5
        assert payload["page"] == 2
        assert payload["page_size"] == 2
        assert payload["total_pages"] == 3
        assert len(payload["items"]) == 2


# ---------------------------------------------------------------------------
# Crawler XML/JSON parsing
# ---------------------------------------------------------------------------

class TestCrawlerParsing:
    def test_xinhua_parses_rss_xml(self):
        import asyncio
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Xinhua Finance</title>
    <item>
      <title>央行宣布降准 0.5 个百分点</title>
      <link>https://example.com/a</link>
      <guid>https://example.com/a</guid>
      <pubDate>Wed, 01 Jul 2026 06:00:00 +0800</pubDate>
      <description>中国人民银行决定下调存款准备金率 0.5 个百分点</description>
      <author>新华社</author>
    </item>
    <item>
      <title>无链接占位</title>
    </item>
  </channel>
</rss>"""
        crawler = XinhuaCrawler()
        articles = asyncio.run(crawler.parse(_fake_response(xml)))
        assert len(articles) == 1
        a = articles[0]
        assert a.source == "xinhua_rss"
        assert "央行" in a.title
        assert a.url == "https://example.com/a"
        # pubDate was China TZ; we convert to UTC.
        assert a.published_at.tzinfo is not None
        # Description has no HTML tags after strip.
        assert a.body is not None and "<" not in a.body

    def test_xinhua_handles_broken_xml(self):
        import asyncio
        crawler = XinhuaCrawler()
        assert asyncio.run(crawler.parse(_fake_response("not xml"))) == []

    def test_cninfo_parses_announcement_payload(self):
        import asyncio
        payload = {
            "announcements": [
                {
                    "announcementId": 12345,
                    "announcementTitle": "<em>贵州茅台</em>2026 年第三季度报告",
                    "adjunctUrl": "/finalpage/2026-07-01/123.PDF",
                    "announcementTime": 1720051200000,  # 2024-07-04T00:00:00Z
                    "secCode": "600519",
                    "secName": "贵州茅台",
                    "category": "category_sjdbg_szsh",
                },
                {"announcementTitle": "", "adjunctUrl": ""},  # skipped
            ]
        }
        crawler = CninfoCrawler()
        articles = asyncio.run(crawler.parse(payload))
        assert len(articles) == 1
        a = articles[0]
        assert a.source == "cninfo"
        assert a.url == "http://static.cninfo.com.cn/finalpage/2026-07-01/123.PDF"
        assert a.extra["stock_code"] == "600519"
        assert a.extra["stock_name"] == "贵州茅台"
        # Title is HTML-stripped.
        assert "<em>" not in a.title

    def test_sina_parses_roll_payload(self):
        import asyncio
        payload = {
            "result": {
                "data": [
                    {
                        "id": "abc123",
                        "title": "央行宣布降准",
                        "url": "https://finance.sina.com.cn/news/1",
                        "ctime": 1720051200,
                        "intro": "中国人民银行决定...",
                        "media_name": "新华社",
                    },
                    {"title": "", "url": ""},  # skipped
                ]
            }
        }
        crawler = SinaCrawler()
        articles = asyncio.run(crawler.parse(payload))
        assert len(articles) == 1
        a = articles[0]
        assert a.source == "sina_finance"
        assert a.author == "新华社"
        assert a.body == "中国人民银行决定..."


def _fake_response(text: str):
    """Build a :class:`_Response`-shaped object for parse() calls."""
    from app.services.news.crawler.base import _Response

    return _Response(url="test://", text=text, content=text.encode("utf-8"),
                     status_code=200, headers={})
