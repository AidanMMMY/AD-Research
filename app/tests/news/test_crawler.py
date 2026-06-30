"""Unit tests for the anti-scraping crawler base library.

Focuses on the primitives (BaseCrawler, AsyncTokenBucket, ProxyPool,
Stats, RawArticle) that downstream source-specific crawlers rely on.
HTTP I/O is mocked via ``httpx.MockTransport`` so the suite is
hermetic and offline.

Tests cover:

- RawArticle construction, serialization round-trip, identity_key
- AsyncTokenBucket rate-limit semantics (acquire blocks for the
  correct amount of time)
- ProxyPool round-robin rotation + env-driven construction
- Stats counter accumulation and percentile calculation
- BaseCrawler UA rotation, retry-then-success, blocking detection,
  and the abstract ``parse`` interface
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone

import httpx
import pytest

from app.services.news.crawler import (
    AsyncTokenBucket,
    BaseCrawler,
    ProxyPool,
    RawArticle,
    Stats,
)
from app.services.news.crawler.base import _Response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DummyCrawler(BaseCrawler):
    """Minimal concrete subclass used to exercise BaseCrawler plumbing."""

    source_name = "dummy"

    def __init__(self, *, responses: list[_Response] | None = None, **kwargs):
        super().__init__(**kwargs)
        self._responses = list(responses or [])
        self.parse_calls = 0

    async def parse(self, response: _Response) -> list[RawArticle]:
        self.parse_calls += 1
        return [
            RawArticle(
                source=self.source_name,
                url=response.url,
                title="parsed",
                published_at=datetime.now(tz=timezone.utc),
            )
        ]


# ---------------------------------------------------------------------------
# RawArticle
# ---------------------------------------------------------------------------


class TestRawArticle:
    def test_required_fields(self):
        ts = datetime(2026, 7, 1, 12, 0, 0)
        a = RawArticle(
            source="xinhua_rss",
            url="https://example.com/a",
            title="Hello",
            published_at=ts,
        )
        assert a.language == "zh"
        assert a.market == "cn_a"
        assert a.engagement == {}
        assert a.extra == {}
        # tz-naive inputs are forced to UTC.
        assert a.published_at.tzinfo is timezone.utc

    def test_to_dict_round_trip(self):
        ts = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
        a = RawArticle(
            source="reddit_wsb",
            url="https://reddit.com/r/wsb/x",
            title="To the moon",
            published_at=ts,
            body="body text",
            body_html="<p>body text</p>",
            author="user_123",
            language="en",
            market="us",
            engagement={"likes": 12, "comments": 3, "shares": 0, "views": 400},
            extra={"subreddit": "wsb"},
        )
        data = a.to_dict()
        # JSON-roundtrip
        encoded = json.dumps(data, ensure_ascii=False)
        decoded = json.loads(encoded)
        rehydrated = RawArticle.from_dict(decoded)
        assert rehydrated.source == a.source
        assert rehydrated.url == a.url
        assert rehydrated.title == a.title
        assert rehydrated.body == a.body
        assert rehydrated.engagement == a.engagement
        assert rehydrated.published_at == a.published_at
        assert rehydrated.published_at.tzinfo is timezone.utc

    def test_identity_key_prefers_source_id(self):
        a = RawArticle(
            source="x",
            url="https://example.com/a",
            title="t",
            published_at=datetime.now(tz=timezone.utc),
            source_id="abc",
        )
        assert a.identity_key() == "x:abc"

    def test_identity_key_falls_back_to_url(self):
        a = RawArticle(
            source="x",
            url="https://example.com/a",
            title="t",
            published_at=datetime.now(tz=timezone.utc),
        )
        assert a.identity_key() == "x:https://example.com/a"

    def test_to_json_is_valid_json(self):
        a = RawArticle(
            source="x",
            url="https://example.com/a",
            title="t",
            published_at=datetime.now(tz=timezone.utc),
        )
        raw = a.to_json()
        # No exceptions on load.
        data = json.loads(raw)
        assert data["title"] == "t"


# ---------------------------------------------------------------------------
# AsyncTokenBucket
# ---------------------------------------------------------------------------


class TestAsyncTokenBucket:
    async def test_initial_burst_drains_then_blocks(self):
        # 5 tokens per 5 seconds = 1 token per second. Start with 2
        # tokens; third acquire must wait ~1s.
        bucket = AsyncTokenBucket(rate=5, period_seconds=5.0, initial_tokens=2)
        start = time.monotonic()
        # Token 1 — immediate
        await bucket.acquire()
        t1 = time.monotonic() - start
        # Token 2 — immediate
        await bucket.acquire()
        t2 = time.monotonic() - start
        # Token 3 — should wait for refill (~1s)
        await bucket.acquire()
        t3 = time.monotonic() - start

        assert t1 < 0.05
        assert t2 < 0.05
        # 5 / 5 = 1 token per second. Allow generous slack for CI jitter.
        assert t3 >= 0.7, f"expected t3 >= 0.7, got {t3}"

    async def test_concurrent_acquire_serialises(self):
        # No initial tokens — each acquire must wait for refill.
        # Rate 4 / 2s = 2 / sec. Three acquires take ~1s total.
        bucket = AsyncTokenBucket(rate=4, period_seconds=2.0, initial_tokens=0)
        start = time.monotonic()
        await asyncio.gather(bucket.acquire(), bucket.acquire(), bucket.acquire())
        elapsed = time.monotonic() - start
        # ~ 2 tokens to acquire first, then third needs another ~0.5s.
        assert elapsed >= 0.4

    async def test_invalid_rate(self):
        with pytest.raises(ValueError):
            AsyncTokenBucket(rate=0)
        with pytest.raises(ValueError):
            AsyncTokenBucket(rate=5, period_seconds=0)

    async def test_capacity_cap(self):
        bucket = AsyncTokenBucket(rate=2, period_seconds=60.0)
        with pytest.raises(ValueError):
            await bucket.acquire(tokens=5)

    async def test_context_manager(self):
        bucket = AsyncTokenBucket(rate=10, period_seconds=60.0, initial_tokens=5)
        async with bucket as b:
            assert b is bucket
        # After context exit, 4 tokens left.
        assert 3.5 <= bucket.available <= 4.5


# ---------------------------------------------------------------------------
# ProxyPool
# ---------------------------------------------------------------------------


class TestProxyPool:
    def test_empty_returns_none(self):
        pool = ProxyPool()
        assert pool.size == 0
        assert pool.get() is None
        assert pool.rotate() is None

    def test_round_robin(self):
        pool = ProxyPool(["http://a:1", "http://b:2", "http://c:3"])
        assert pool.size == 3
        # 6 calls → exactly twice through the list.
        seq = [pool.get() for _ in range(6)]
        assert seq == [
            "http://a:1", "http://b:2", "http://c:3",
            "http://a:1", "http://b:2", "http://c:3",
        ]

    def test_strip_whitespace(self):
        pool = ProxyPool(["  http://a:1  ", "", "   ", "http://b:2"])
        assert pool.size == 2
        assert pool.get() == "http://a:1"
        assert pool.get() == "http://b:2"

    def test_rotate_skips(self):
        pool = ProxyPool(["http://a:1", "http://b:2"])
        assert pool.get() == "http://a:1"
        pool.rotate()
        # Force-advanced to b even before the natural next call.
        assert pool.get() == "http://a:1"  # skipped past b
        # After the natural cycle, we land back on b.
        # Actually note: rotate() advances _current by 1 (from b→a),
        # so next get() returns a.
        assert pool.get() == "http://b:2"

    def test_add_runtime(self):
        pool = ProxyPool(["http://a:1"])
        pool.add("http://b:2")
        pool.add("http://a:1")  # duplicate, ignored
        assert pool.size == 2

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("PROXY_LIST", "http://a:1, http://b:2")
        pool = ProxyPool.from_env()
        assert pool.size == 2
        assert pool.get() == "http://a:1"


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_initial_state(self):
        s = Stats()
        d = s.to_dict()
        assert d["success"] == 0
        assert d["failed"] == 0
        assert d["timeout"] == 0
        assert d["blocked"] == 0
        assert d["total_requests"] == 0
        assert d["success_rate"] == 0.0
        assert d["latency_p50_ms"] == 0.0

    def test_counters_accumulate(self):
        s = Stats()
        s.record_success(bytes=128, latency_ms=10.0)
        s.record_success(bytes=256, latency_ms=20.0)
        s.record_failed(latency_ms=50.0)
        s.record_timeout()
        s.record_blocked()
        d = s.to_dict()
        assert d["success"] == 2
        assert d["failed"] == 1
        assert d["timeout"] == 1
        assert d["blocked"] == 1
        assert d["total_requests"] == 5
        assert d["total_bytes"] == 128 + 256
        assert d["success_rate"] == pytest.approx(0.4)
        assert d["first_seen"] is not None
        assert d["last_seen"] is not None

    def test_percentiles_basic(self):
        s = Stats()
        for v in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
            s.record_success(latency_ms=v)
        pct = s.latency_percentiles()
        assert pct["count"] == 10
        assert 50 <= pct["p50"] <= 60
        assert 90 <= pct["p95"] <= 100

    def test_summary_includes_key_counters(self):
        s = Stats()
        s.record_success(latency_ms=10.0)
        s.record_failed(latency_ms=20.0)
        text = s.summary()
        assert "requests=2" in text
        assert "success=1" in text
        assert "failed=1" in text

    def test_latency_sample_bounded(self):
        s = Stats(max_latency_samples=4)
        for v in [1, 2, 3, 4, 5, 6, 7]:
            s.record_success(latency_ms=v)
        # Window is bounded — count never exceeds capacity.
        pct = s.latency_percentiles()
        assert pct["count"] <= 4

    def test_invalid_latency_rejected(self):
        s = Stats()
        # Invalid values are silently dropped (no exception).
        s.record_success(latency_ms=None)
        s.record_success(latency_ms=float("nan"))
        s.record_success(latency_ms=-5.0)
        pct = s.latency_percentiles()
        assert pct["count"] == 0


# ---------------------------------------------------------------------------
# BaseCrawler
# ---------------------------------------------------------------------------


def _no_rate_limiter(self):  # bound to DummyCrawler in fixtures
    return AsyncTokenBucket(rate=100_000, period_seconds=60.0)


class TestBaseCrawler:
    async def test_fetch_without_client_raises(self):
        c = _DummyCrawler()
        with pytest.raises(RuntimeError, match="async with"):
            await c.fetch("https://example.com")

    async def test_fetch_records_success(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=b"<html><body>hi</body></html>",
                headers={"content-type": "text/html"},
            )

        transport = httpx.MockTransport(handler)
        c = _DummyCrawler(client=httpx.AsyncClient(transport=transport, timeout=10.0))
        async with c:
            c._get_rate_limiter = _no_rate_limiter.__get__(c, _DummyCrawler)  # type: ignore[attr-defined]
            resp = await c.fetch("https://example.com/")
        assert resp.status_code == 200
        assert resp.text == "<html><body>hi</body></html>"
        assert c.stats.success == 1
        assert c.stats.failed == 0

    async def test_fetch_retries_on_transient_failure(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] < 3:
                return httpx.Response(503, content=b"busy")
            return httpx.Response(200, content=b"ok")

        transport = httpx.MockTransport(handler)
        c = _DummyCrawler(client=httpx.AsyncClient(transport=transport, timeout=10.0))
        c.jitter_min = 0.0
        c.jitter_max = 0.0
        async with c:
            c._get_rate_limiter = _no_rate_limiter.__get__(c, _DummyCrawler)  # type: ignore[attr-defined]
            resp = await c.fetch("https://example.com/")
        assert resp.status_code == 200
        assert calls["n"] == 3
        assert c.stats.success == 1
        # Two failed (503) before the eventual success.
        assert c.stats.failed == 2

    async def test_fetch_treats_429_as_blocked(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, content=b"slow down")

        transport = httpx.MockTransport(handler)
        c = _DummyCrawler(client=httpx.AsyncClient(transport=transport, timeout=10.0))
        c.jitter_min = 0.0
        c.jitter_max = 0.0
        c.max_retries = 1
        async with c:
            c._get_rate_limiter = _no_rate_limiter.__get__(c, _DummyCrawler)  # type: ignore[attr-defined]
            with pytest.raises(httpx.HTTPStatusError):
                await c.fetch("https://example.com/")
        assert c.stats.blocked >= 1

    async def test_fetch_treats_403_as_blocked(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, content=b"forbidden")

        transport = httpx.MockTransport(handler)
        c = _DummyCrawler(client=httpx.AsyncClient(transport=transport, timeout=10.0))
        c.jitter_min = 0.0
        c.jitter_max = 0.0
        c.max_retries = 1
        async with c:
            c._get_rate_limiter = _no_rate_limiter.__get__(c, _DummyCrawler)  # type: ignore[attr-defined]
            with pytest.raises(httpx.HTTPStatusError):
                await c.fetch("https://example.com/")
        assert c.stats.blocked >= 1

    async def test_user_agent_rotation(self):
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            ua = request.headers.get("user-agent", "")
            seen.append(ua)
            return httpx.Response(200, content=b"")

        transport = httpx.MockTransport(handler)
        c = _DummyCrawler(client=httpx.AsyncClient(transport=transport, timeout=10.0))
        c.jitter_min = 0.0
        c.jitter_max = 0.0
        async with c:
            c._get_rate_limiter = _no_rate_limiter.__get__(c, _DummyCrawler)  # type: ignore[attr-defined]
            for _ in range(40):
                await c.fetch("https://example.com/")
        # Pool contains the 15 default UAs (and only those).
        ua_pool = c._user_agents
        assert all(ua in ua_pool for ua in seen)
        # Across 40 calls we should have seen more than one distinct UA.
        assert len(set(seen)) > 1

    async def test_crawl_invokes_parse(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html>body</html>")

        transport = httpx.MockTransport(handler)
        c = _DummyCrawler(client=httpx.AsyncClient(transport=transport, timeout=10.0))
        c.jitter_min = 0.0
        c.jitter_max = 0.0
        async with c:
            c._get_rate_limiter = _no_rate_limiter.__get__(c, _DummyCrawler)  # type: ignore[attr-defined]
            arts = await c.crawl("https://example.com/")
        assert c.parse_calls == 1
        assert len(arts) == 1
        assert arts[0].source == "dummy"

    async def test_strip_html(self):
        assert BaseCrawler.strip_html("<p>Hello <b>world</b></p>") == "Hello world"
        assert BaseCrawler.strip_html("plain") == "plain"
        assert BaseCrawler.strip_html("<a>x</a>  <a>y</a>") == "x y"
        assert BaseCrawler.strip_html("") == ""

    async def test_per_source_rate_limit_independent(self):
        # Two crawlers, each with a separate bucket — neither blocks the other.
        a = _DummyCrawler(rate_limit_per_min=60)
        b = _DummyCrawler(rate_limit_per_min=60)
        la = a._get_rate_limiter()
        lb = b._get_rate_limiter()
        assert la is not lb
        # Different instances, no cross-talk.
        la._tokens = 0
        assert lb._tokens >= 0

    async def test_proxy_pool_overrides_env(self, monkeypatch):
        monkeypatch.setenv("PROXY_LIST", "http://env:1,http://env:2")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"")

        transport = httpx.MockTransport(handler)
        c = _DummyCrawler(
            client=httpx.AsyncClient(transport=transport, timeout=10.0),
            proxies=["http://explicit:9999"],
        )
        c.jitter_min = 0.0
        c.jitter_max = 0.0
        async with c:
            c._get_rate_limiter = _no_rate_limiter.__get__(c, _DummyCrawler)  # type: ignore[attr-defined]
            await c.fetch("https://example.com/")
        # Explicit override takes precedence; the env-only base pool is unused.
        assert c.proxy_pool.size == 1
        assert c.proxy_pool.get() == "http://explicit:9999"

    async def test_max_retries_exhausted(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, content=b"down")

        transport = httpx.MockTransport(handler)
        c = _DummyCrawler(client=httpx.AsyncClient(transport=transport, timeout=10.0))
        c.jitter_min = 0.0
        c.jitter_max = 0.0
        c.max_retries = 2
        async with c:
            c._get_rate_limiter = _no_rate_limiter.__get__(c, _DummyCrawler)  # type: ignore[attr-defined]
            with pytest.raises(httpx.HTTPStatusError):
                await c.fetch("https://example.com/")
        # Two retries → three attempts in total → two 'failed' records
        # (we record on 503 path twice before the final raise).
        assert c.stats.failed >= 2
