"""Tests for YahooFinanceCrawler → Finnhub fallback.

Yahoo Finance has been observed to return HTTP 429 (and occasionally
403) to non-browser user agents from its edge infrastructure. To keep
the daily news crawl resilient, the Yahoo crawler transparently
falls back to Finnhub's ``/company-news`` endpoint when the primary
fetch is rejected. These tests cover the four behaviours we care
about:

1. 429 → fallback to Finnhub, articles come from Finnhub.
2. 403 → same fallback path.
3. No ``FINNHUB_API_KEY`` → fallback is silent; the ticker contributes
   no articles but the rest of the batch still succeeds.
4. Yahoo 200 → Finnhub is never called (no regression to the happy
   path).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

import httpx
import pytest

from app.services.news.crawler.rate_limiter import AsyncTokenBucket
from app.services.news.sources.yahoo_rss import (
    YAHOO_RSS_URL,
    YahooFinanceCrawler,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def no_rate_limit() -> AsyncTokenBucket:
    return AsyncTokenBucket(rate=10_000, period_seconds=60.0)


def _client_for(handler) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, timeout=10.0)


class FakeFinnhubProvider:
    """Drop-in replacement for :class:`FinnhubProvider`."""

    def __init__(
        self,
        *,
        articles: list[dict[str, Any]] | None = None,
        raise_on_call: Exception | None = None,
        calls: list[tuple[str, date, date]] | None = None,
    ) -> None:
        self._articles = articles or []
        self._raise = raise_on_call
        self.calls = calls if calls is not None else []

    def fetch_company_news(
        self, code: str, from_date: date, to_date: date
    ) -> list[dict[str, Any]]:
        self.calls.append((code, from_date, to_date))
        if self._raise is not None:
            raise self._raise
        return list(self._articles)


def _sample_finnhub_article(
    *,
    headline: str = "Apple beats earnings",
    summary: str = "Strong services growth.",
    url: str = "https://example.com/apple-beats",
    source: str = "ExampleNews",
    category: str = "company",
    unix_ts: int = 1735689600,
) -> dict[str, Any]:
    return {
        "headline": headline,
        "summary": summary,
        "url": url,
        "datetime": unix_ts,
        "source": source,
        "category": category,
    }


# ---------------------------------------------------------------------------
# 1. 429 → fallback success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yahoo_429_falls_back_to_finnhub(
    no_rate_limit, monkeypatch
):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")

    yahoo_calls: list[str] = []
    provider = FakeFinnhubProvider(
        articles=[
            _sample_finnhub_article(
                headline="Apple beats $AAPL earnings",
                summary="$MSFT unaffected.",
                unix_ts=1735689600,
            ),
            _sample_finnhub_article(
                headline="Apple announces buyback",
                url="https://example.com/buyback",
                unix_ts=1735776000,
            ),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(YAHOO_RSS_URL):
            yahoo_calls.append(str(request.url))
            return httpx.Response(429, text="Too Many Requests")
        return httpx.Response(500, text="unexpected")

    client = _client_for(handler)
    try:
        crawler = YahooFinanceCrawler(
            client=client,
            rate_limiter=no_rate_limit,
            finnhub_provider=provider,
        )
        arts = await crawler.fetch("AAPL")
    finally:
        await client.aclose()

    # Yahoo was called exactly once for AAPL.
    assert len(yahoo_calls) == 1
    assert "s=AAPL" in yahoo_calls[0]

    # Finnhub was called once for AAPL with a sensible date range.
    assert len(provider.calls) == 1
    code, from_date, to_date = provider.calls[0]
    assert code == "AAPL"
    assert to_date == date.today()
    assert (to_date - from_date).days == 7

    # Articles came from the Finnhub fallback path.
    assert len(arts) == 2
    for art in arts:
        # Yahoo's fallback now shares the primary ``yahoo_finance``
        # source name so the news-health aggregator counts it under
        # the same bucket as the RSS path. The fallback provenance is
        # still preserved in ``extra["fallback_from"]``.
        assert art.source == "yahoo_finance"
        assert art.extra.get("fallback_from") == "yahoo_finance"
        assert art.extra.get("ticker") == "AAPL"
        # published_at should be a UTC-aware datetime.
        assert art.published_at.tzinfo is not None
        assert art.published_at == art.published_at.astimezone(timezone.utc)

    titles = [a.title for a in arts]
    assert "Apple beats $AAPL earnings" in titles
    assert "Apple announces buyback" in titles
    # Symbol extraction runs over title + body — AAPL ticker from the
    # cashtag + the explicit ticker argument, MSFT from the body.
    syms = set(arts[0].engagement.get("symbols_extracted", []))
    assert "AAPL.US" in syms
    assert "MSFT.US" in syms


# ---------------------------------------------------------------------------
# 2. 403 also triggers the fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yahoo_403_falls_back_to_finnhub(no_rate_limit, monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    provider = FakeFinnhubProvider(
        articles=[
            _sample_finnhub_article(
                headline="TSLA in the news",
                url="https://example.com/tsla-1",
            )
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(YAHOO_RSS_URL):
            return httpx.Response(403, text="Forbidden")
        return httpx.Response(500, text="unexpected")

    client = _client_for(handler)
    try:
        crawler = YahooFinanceCrawler(
            client=client,
            rate_limiter=no_rate_limit,
            finnhub_provider=provider,
        )
        arts = await crawler.fetch(["TSLA"])
    finally:
        await client.aclose()

    assert len(provider.calls) == 1
    assert provider.calls[0][0] == "TSLA"
    assert len(arts) == 1
    assert arts[0].source == "yahoo_finance"
    assert arts[0].extra["ticker"] == "TSLA"
    assert arts[0].extra["fallback_from"] == "yahoo_finance"


# ---------------------------------------------------------------------------
# 3. No API key → silent skip (with warning), other tickers keep going
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yahoo_429_without_finnhub_key_returns_empty_for_ticker(
    no_rate_limit, monkeypatch, caplog
):
    # Force the key to an empty string. We can't ``delenv`` because
    # the project .env file ships a real key, and pydantic-settings
    # will reload it on the next ``Settings()`` instantiation.
    monkeypatch.setenv("FINNHUB_API_KEY", "")
    from app.config import get_settings

    get_settings.cache_clear()

    yahoo_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(YAHOO_RSS_URL):
            yahoo_calls.append(str(request.url))
            return httpx.Response(429, text="Too Many Requests")
        return httpx.Response(500, text="unexpected")

    client = _client_for(handler)
    try:
        crawler = YahooFinanceCrawler(
            client=client,
            rate_limiter=no_rate_limit,
            # No finnhub_provider injected; key missing → silent skip.
        )
        with caplog.at_level("WARNING"):
            arts = await crawler.fetch(["AAPL"])
    finally:
        get_settings.cache_clear()  # don't leak into other tests
        await client.aclose()

    # Yahoo was called; the fallback was skipped because no key.
    assert len(yahoo_calls) == 1
    # No articles, but no exception either.
    assert arts == []
    # Operator-facing log makes the failure mode obvious.
    assert any(
        "FINNHUB_API_KEY is not set" in rec.message for rec in caplog.records
    )


@pytest.mark.asyncio
async def test_yahoo_429_no_key_does_not_break_other_tickers(
    no_rate_limit, monkeypatch
):
    """One ticker falling into the no-key fallback must not poison the batch."""
    monkeypatch.setenv("FINNHUB_API_KEY", "")
    from app.config import get_settings

    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if not url.startswith(YAHOO_RSS_URL):
            return httpx.Response(500, text="unexpected")
        # AAPL blocked; TSLA succeeds normally.
        if "s=AAPL" in url:
            return httpx.Response(429, text="Too Many Requests")
        if "s=TSLA" in url:
            body = (
                "<rss version=\"2.0\">"
                "<channel><title>TSLA</title>"
                "<item><title>Tesla jumps</title>"
                "<link>https://example.com/tesla</link>"
                "<guid>t1</guid>"
                "<pubDate>Mon, 30 Jun 2026 13:30:00 +0000</pubDate>"
                "<description>Tesla rallied.</description>"
                "</item></channel></rss>"
            )
            return httpx.Response(200, text=body)
        return httpx.Response(404, text="not found")

    client = _client_for(handler)
    try:
        crawler = YahooFinanceCrawler(
            client=client,
            rate_limiter=no_rate_limit,
        )
        arts = await crawler.fetch(["AAPL", "TSLA"])
    finally:
        get_settings.cache_clear()
        await client.aclose()

    # Only the TSLA article survives.
    assert len(arts) == 1
    assert arts[0].source == "yahoo_finance"
    assert arts[0].extra["ticker"] == "TSLA"


# ---------------------------------------------------------------------------
# 4. Yahoo happy path → no Finnhub call (no regression)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yahoo_200_does_not_call_finnhub(no_rate_limit, monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    provider = FakeFinnhubProvider(articles=[])

    def handler(request: httpx.Request) -> httpx.Response:
        body = (
            "<rss version=\"2.0\"><channel><title>AAPL</title>"
            "<item><title>Apple rises on $AAPL news</title>"
            "<link>https://finance.yahoo.com/news/aapl-1</link>"
            "<guid>y1</guid>"
            "<pubDate>Mon, 30 Jun 2026 13:30:00 +0000</pubDate>"
            "<description>Rising tide.</description>"
            "</item></channel></rss>"
        )
        return httpx.Response(200, text=body)

    client = _client_for(handler)
    try:
        crawler = YahooFinanceCrawler(
            client=client,
            rate_limiter=no_rate_limit,
            finnhub_provider=provider,
        )
        arts = await crawler.fetch(["AAPL"])
    finally:
        await client.aclose()

    assert len(arts) == 1
    assert arts[0].source == "yahoo_finance"
    assert arts[0].extra["ticker"] == "AAPL"
    # Critical: the fallback must not be invoked when Yahoo succeeds.
    assert provider.calls == []


# ---------------------------------------------------------------------------
# 5. Finnhub returns nothing → empty list, no crash
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finnhub_fallback_empty_result(no_rate_limit, monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    provider = FakeFinnhubProvider(articles=[])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Too Many Requests")

    client = _client_for(handler)
    try:
        crawler = YahooFinanceCrawler(
            client=client,
            rate_limiter=no_rate_limit,
            finnhub_provider=provider,
        )
        arts = await crawler.fetch(["AAPL"])
    finally:
        await client.aclose()

    assert arts == []
    assert len(provider.calls) == 1


# ---------------------------------------------------------------------------
# 6. Finnhub raises → swallow, no crash, no articles for the ticker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finnhub_fallback_exception_swallowed(no_rate_limit, monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    provider = FakeFinnhubProvider(
        raise_on_call=RuntimeError("upstream down"),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Too Many Requests")

    client = _client_for(handler)
    try:
        crawler = YahooFinanceCrawler(
            client=client,
            rate_limiter=no_rate_limit,
            finnhub_provider=provider,
        )
        arts = await crawler.fetch(["AAPL"])
    finally:
        await client.aclose()

    assert arts == []
    assert len(provider.calls) == 1


# ---------------------------------------------------------------------------
# 7. Finnhub 500 (server error) does NOT trigger the fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yahoo_500_propagates_no_fallback(no_rate_limit, monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    provider = FakeFinnhubProvider(articles=[])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    client = _client_for(handler)
    try:
        crawler = YahooFinanceCrawler(
            client=client,
            rate_limiter=no_rate_limit,
            finnhub_provider=provider,
        )
        arts = await crawler.fetch(["AAPL"])
    finally:
        await client.aclose()

    # Server errors are not in the fallback set — the failure is
    # swallowed by the outer try/except in fetch() and contributes no
    # articles, but the Finnhub provider must not have been called.
    assert arts == []
    assert provider.calls == []
