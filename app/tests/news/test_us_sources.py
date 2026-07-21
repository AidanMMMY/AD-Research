"""Unit tests for the four US news crawlers.

Covers:
  * Yahoo Finance RSS XML parsing (per-ticker, multi-ticker)
  * CNBC RSS XML parsing
  * SEC EDGAR submissions JSON parsing
  * Reddit listing JSON parsing + upvote_ratio sentiment proxy
  * Symbol extraction rules used by every source

The HTTP layer is mocked via ``httpx.MockTransport`` so the tests are
hermetic and never touch the public Internet. Rate-limiters are
substituted with a no-op so the tests don't have to wait for the
token bucket to drain.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from app.services.news.crawler.rate_limiter import AsyncTokenBucket
from app.services.news.crawler.symbol_extractor import extract_symbols
from app.services.news.sources.cnbc import CNBCCrawler
from app.services.news.sources.reddit import (
    DEFAULT_SUBREDDIT_PLAN,
    TICKER_SUBREDDITS,
    RedditCrawler,
    _post_to_article,
)
from app.services.news.sources.sec_edgar import SUPPORTED_FORMS, SecEdgarCrawler, _parse_submissions
from app.services.news.sources.yahoo_rss import YahooFinanceCrawler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def no_rate_limit() -> AsyncTokenBucket:
    """Bucket with extremely high rate so tests don't wait."""
    return AsyncTokenBucket(rate=10_000, period_seconds=60.0)


def _client_for(handler) -> httpx.AsyncClient:
    """Return an ``httpx.AsyncClient`` whose transport is the given handler."""
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, timeout=10.0)


# ---------------------------------------------------------------------------
# Yahoo Finance
# ---------------------------------------------------------------------------


YAHU_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>Yahoo Finance - AAPL</title>
    <link>https://finance.yahoo.com/quote/AAPL</link>
    <description>Headlines for AAPL</description>
    <language>en-US</language>
    <item>
      <title>Apple beats earnings as $AAPL services surge</title>
      <link>https://finance.yahoo.com/news/apple-beats-123.html</link>
      <guid isPermaLink="false">yahoo-aapl-1</guid>
      <pubDate>Mon, 30 Jun 2026 13:30:00 +0000</pubDate>
      <description><![CDATA[ Apple reported strong services growth. ]]></description>
      <dc:creator>Yahoo Finance</dc:creator>
    </item>
    <item>
      <title>iPhone unit sales disappoint, MSFT unaffected</title>
      <link>https://finance.yahoo.com/news/iphone-unit-456.html</link>
      <guid isPermaLink="false">yahoo-aapl-2</guid>
      <pubDate>Mon, 30 Jun 2026 14:10:00 +0000</pubDate>
      <description>iPhone unit sales disappointed this quarter.</description>
    </item>
  </channel>
</rss>
"""


@pytest.mark.asyncio
async def test_yahoo_rss_parses_articles(no_rate_limit):
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        return httpx.Response(200, text=YAHU_RSS_XML)

    client = _client_for(handler)
    try:
        crawler = YahooFinanceCrawler(client=client, rate_limiter=no_rate_limit)
        arts = await crawler.fetch("AAPL")
    finally:
        await client.aclose()

    assert len(arts) == 2
    titles = [a.title for a in arts]
    assert any("Apple beats" in t for t in titles)
    assert any("iPhone unit" in t for t in titles)
    assert all(a.source == "yahoo_finance" for a in arts)
    # Symbols: AAPL from cashtag + ticker arg, MSFT from body.
    sym_sets = [set(a.engagement.get("symbols_extracted", [])) for a in arts]
    assert any("AAPL.US" in s for s in sym_sets)
    assert any("MSFT.US" in s for s in sym_sets)
    # Date parsed to UTC.
    assert all(a.published_at.tzinfo is not None for a in arts)
    assert all(a.published_at == a.published_at.astimezone(timezone.utc) for a in arts)
    assert any("rss/2.0/headline" in u and "s=AAPL" in u for u in captured)


@pytest.mark.asyncio
async def test_yahoo_rss_handles_multi_ticker(no_rate_limit):
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        # Use ticker in URL to vary the body.
        s = request.url.params.get("s", "AAPL")
        body = YAHU_RSS_XML.replace("AAPL", s)
        return httpx.Response(200, text=body)

    client = _client_for(handler)
    try:
        crawler = YahooFinanceCrawler(client=client, rate_limiter=no_rate_limit)
        arts = await crawler.fetch(["AAPL", "TSLA"])
    finally:
        await client.aclose()

    assert call_count["n"] == 2
    assert len(arts) == 4  # 2 tickers × 2 articles
    tickers = {a.extra.get("ticker") for a in arts}
    assert tickers == {"AAPL", "TSLA"}


# ---------------------------------------------------------------------------
# CNBC
# ---------------------------------------------------------------------------


CNBC_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>CNBC Top News</title>
    <link>https://www.cnbc.com</link>
    <item>
      <title>Fed signals rate cut as $SPY rallies</title>
      <link>https://www.cnbc.com/2026/06/30/fed-rate-cut.html</link>
      <guid isPermaLink="false">cnbc-1</guid>
      <pubDate>Mon, 30 Jun 2026 15:00:00 +0000</pubDate>
      <description>Stocks rallied after the Fed hinted at a rate cut.</description>
      <dc:creator>Jeff Cox</dc:creator>
      <category>Top News</category>
    </item>
  </channel>
</rss>
"""


@pytest.mark.asyncio
async def test_cnbc_parses(no_rate_limit):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=CNBC_RSS_XML)

    client = _client_for(handler)
    try:
        crawler = CNBCCrawler(client=client, rate_limiter=no_rate_limit)
        arts = await crawler.fetch()
    finally:
        await client.aclose()

    assert len(arts) == 1
    art = arts[0]
    assert art.source == "cnbc"
    assert "Fed signals" in art.title
    assert art.author == "Jeff Cox"
    assert art.extra.get("category") == "Top News"
    assert "SPY.US" in art.engagement.get("symbols_extracted", [])
    # HTML should be stripped from body.
    assert "<" not in (art.body or "")


# ---------------------------------------------------------------------------
# SEC EDGAR
# ---------------------------------------------------------------------------


def _sec_submissions_payload() -> dict:
    return {
        "cik": "320193",
        "name": "Apple Inc.",
        "filings": {
            "recent": {
                "form": ["8-K", "10-Q", "4", "S-1"],
                "accessionNumber": [
                    "0000320193-26-000123",
                    "0000320193-26-000090",
                    "0000320193-26-000050",
                    "0000320193-26-000010",
                ],
                "primaryDocument": [
                    "d12345.htm",
                    "d90001.htm",
                    "d50001.htm",
                    "d10001.htm",
                ],
                "filingDate": ["2026-06-30", "2026-05-01", "2026-04-15", "2026-03-20"],
                "reportDate": ["2026-06-30", "2026-03-31", "", ""],
                "primaryDocDescription": [
                    "Current report",
                    "Quarterly report",
                    "",
                    "Registration statement",
                ],
                "items": ["2.02,9.01", "10.01", "", ""],
            }
        },
    }


def test_sec_parse_submissions_filters_forms():
    arts = _parse_submissions(
        _sec_submissions_payload(),
        ticker="AAPL",
        cik="320193",
        forms_keep=SUPPORTED_FORMS,
        since=None,
    )
    forms = {a.extra.get("category") for a in arts}
    assert forms == {"8-K", "10-Q", "S-1"}
    assert all(a.source == "sec_edgar" for a in arts)
    # CIK zero-padded + symbol link.
    assert all(a.extra.get("cik") == "0000320193" for a in arts)
    assert all("AAPL.US" in a.engagement.get("symbols_extracted", []) for a in arts)
    # URL pattern.
    url = arts[0].url
    assert "sec.gov/Archives/edgar/data" in url
    # Accession shows up as both dashed and undashed forms on EDGAR.
    assert "0000320193-26-000123" in url or "000032019326000123" in url


def test_sec_parse_submissions_since_filter():
    cutoff = datetime(2026, 4, 1, tzinfo=timezone.utc)
    arts = _parse_submissions(
        _sec_submissions_payload(),
        ticker="AAPL",
        cik="320193",
        forms_keep=SUPPORTED_FORMS,
        since=cutoff,
    )
    # Only filings on/after April 1.
    assert all(a.published_at >= cutoff for a in arts)
    assert any(a.extra.get("category") == "8-K" for a in arts)  # 2026-06-30


@pytest.mark.asyncio
async def test_sec_fetch_uses_correct_url_and_ua(no_rate_limit, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "TestAgent tester@example.com")
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_sec_submissions_payload())

    client = _client_for(handler)
    try:
        crawler = SecEdgarCrawler(client=client, rate_limiter=no_rate_limit)
        arts = await crawler.fetch({"AAPL": "320193"})
    finally:
        await client.aclose()

    assert len(arts) >= 1
    req = captured[0]
    assert "data.sec.gov/submissions/CIK0000320193.json" in str(req.url)
    assert req.headers.get("user-agent") == "TestAgent tester@example.com"


def test_sec_edgar_default_cik_map_matches_static_reference():
    """The hardcoded crawler CIK map must agree with the SEC-sourced
    static reference (``app/data/static/sec_tickers.json``) for every
    ticker present in both — guards against typos like NVDA -> 1013480
    (the real NVDA CIK is 1045810), which 404 on data.sec.gov."""
    from app.services.news.scheduler_jobs import _SEC_EDGAR_TICKER_TO_CIK

    static_path = (
        Path(__file__).resolve().parents[2] / "data" / "static" / "sec_tickers.json"
    )
    reference = json.loads(static_path.read_text())["tickers"]
    for ticker, cik in _SEC_EDGAR_TICKER_TO_CIK.items():
        if ticker in reference:
            assert str(cik).zfill(10) == reference[ticker]["cik"], (
                f"CIK mismatch for {ticker}"
            )


# ---------------------------------------------------------------------------
# Reddit
# ---------------------------------------------------------------------------


def _reddit_listing(*posts: dict) -> dict:
    return {
        "kind": "Listing",
        "data": {
            "children": [{"kind": "t3", "data": p} for p in posts],
        },
    }


def _reddit_post(
    *,
    title: str = "Sample post",
    selftext: str = "",
    score: int = 100,
    upvote_ratio: float = 0.85,
    num_comments: int = 10,
    subreddit: str = "wallstreetbets",
    flair: str = "DD",
    created_utc: float | None = None,
) -> dict:
    import time as _t

    return {
        "name": "t3_abc123",
        "id": "abc123",
        "title": title,
        "selftext": selftext,
        "permalink": f"/r/{subreddit}/comments/abc123/sample_post/",
        "url_overridden_by_dest": f"https://www.reddit.com/r/{subreddit}/comments/abc123/sample_post/",
        "author": "testuser",
        "score": score,
        "upvote_ratio": upvote_ratio,
        "num_comments": num_comments,
        "link_flair_text": flair,
        "is_self": bool(selftext),
        "is_video": False,
        "gilded": 0,
        "created_utc": created_utc if created_utc is not None else _t.time(),
    }


def test_reddit_post_to_article_symbol_extraction():
    post = _reddit_post(
        title="Tesla to the moon! $TSLA calls printing",
        selftext="Loading up on $TSLA and $NVDA, ignoring $AAPL",
        upvote_ratio=0.92,
        score=1500,
    )
    art = _post_to_article(post, subreddit="wallstreetbets")
    assert art.source == "reddit"
    assert art.title.startswith("Tesla to the moon")
    syms = set(art.engagement.get("symbols_extracted", []))
    assert "TSLA.US" in syms
    assert "NVDA.US" in syms
    assert "AAPL.US" in syms
    # Sentiment proxy: > 0.8 -> bullish.
    assert art.engagement["sentiment_proxy"] == "bullish"
    assert art.engagement["upvote_ratio"] == 0.92
    assert art.engagement["score"] == 1500


def test_reddit_sentiment_proxy_thresholds():
    bull = _post_to_article(_reddit_post(upvote_ratio=0.81), subreddit="stocks")
    mid = _post_to_article(_reddit_post(upvote_ratio=0.65), subreddit="stocks")
    bear = _post_to_article(_reddit_post(upvote_ratio=0.30), subreddit="stocks")
    assert bull.engagement["sentiment_proxy"] == "bullish"
    assert mid.engagement["sentiment_proxy"] == "neutral"
    assert bear.engagement["sentiment_proxy"] == "bearish"


@pytest.mark.asyncio
async def test_reddit_fetch_handles_oauth_and_listing(no_rate_limit, monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "csec")

    token_called = {"n": 0}
    sub_called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://www.reddit.com/api/v1/access_token"):
            token_called["n"] += 1
            assert request.headers.get("authorization", "").startswith("Basic ")
            return httpx.Response(
                200,
                json={"access_token": "tok-123", "expires_in": 3600, "token_type": "bearer"},
            )
        if url.startswith("https://oauth.reddit.com/r/wallstreetbets/hot"):
            sub_called["n"] += 1
            assert request.headers.get("authorization") == "Bearer tok-123"
            return httpx.Response(
                200,
                json=_reddit_listing(
                    _reddit_post(title="$TSLA 1000 eoy", upvote_ratio=0.88, score=200),
                    _reddit_post(title="Macro is rough", upvote_ratio=0.55, score=20),
                ),
            )
        return httpx.Response(404, text="not found")

    client = _client_for(handler)
    try:
        crawler = RedditCrawler(
            client=client,
            rate_limiter=no_rate_limit,
            client_id="cid",
            client_secret="csec",
        )
        arts = await crawler.fetch_subreddit("wallstreetbets", limit=10)
    finally:
        await client.aclose()

    assert token_called["n"] == 1
    assert sub_called["n"] == 1
    assert len(arts) == 2
    assert arts[0].engagement["sentiment_proxy"] == "bullish"
    assert arts[1].engagement["sentiment_proxy"] == "neutral"


@pytest.mark.asyncio
async def test_reddit_universe_plan_iterates(no_rate_limit, monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "csec")

    visited: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "access_token" in url:
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        # Each subreddit listing — extract from URL path: /r/<sub>/hot
        parts = url.split("/r/", 1)
        sub = parts[1].split("/", 1)[0] if len(parts) == 2 else ""
        visited.append(sub)
        return httpx.Response(200, json=_reddit_listing(_reddit_post()))

    client = _client_for(handler)
    try:
        crawler = RedditCrawler(
            client=client,
            rate_limiter=no_rate_limit,
            client_id="cid",
            client_secret="csec",
        )
        arts = await crawler.fetch_universe({"wallstreetbets": 5, "stocks": 5})
    finally:
        await client.aclose()

    assert set(visited) == {"wallstreetbets", "stocks"}
    assert len(arts) == 2


def test_reddit_default_plan_includes_key_subs():
    # Spot-check that the brief's required subs are present.
    for sub in ("wallstreetbets", "stocks", "investing", "options", "cryptocurrency"):
        assert sub in DEFAULT_SUBREDDIT_PLAN
    # Bitcoin + ethereum included.
    assert "bitcoin" in DEFAULT_SUBREDDIT_PLAN
    assert "ethereum" in DEFAULT_SUBREDDIT_PLAN


def test_reddit_ticker_subs_curated():
    # Spot-check — SPY/QQQ have no active dedicated subs so are excluded.
    for t in ("TSLA", "AAPL", "NVDA", "META", "NVDA", "AMD", "GME"):
        assert t in TICKER_SUBREDDITS


# ---------------------------------------------------------------------------
# Symbol extractor
# ---------------------------------------------------------------------------


def test_symbol_extractor_cashtag_and_subreddit():
    s = extract_symbols("Buy $TSLA and $nvda", subreddit="teslamotors", url="https://reddit.com/r/tesla")
    assert "TSLA.US" in s
    assert "NVDA.US" in s
    # r/tesla handle via URL.
    assert "TSLA.US" in s


def test_symbol_extractor_filters_stopwords():
    s = extract_symbols("THE AND FOR YOU ARE NOT")
    # All tokens are stopwords; result should be empty.
    assert s == set()


def test_symbol_extractor_nickname():
    s = extract_symbols("Tesla and Apple are crushing it this quarter")
    assert "TSLA.US" in s
    assert "AAPL.US" in s
