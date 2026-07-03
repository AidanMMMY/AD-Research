"""Tests for the Xueqiu crawler.

These tests are pure-unit — they never make a real network call. The
``httpx`` transport is patched with a fake transport that returns
canned JSON, mirroring the response shapes Xueqiu's web app produces.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from app.services.news.crawler.types import RawArticle
from app.services.news.sources.xueqiu import (
    RawXueqiuPost,
    XueqiuCrawler,
    _parse_xueqiu_time,
    extract_symbols,
    to_xueqiu_symbol,
)
from app.services.news.sources.xueqiu_auth import (
    XUEQIU_BASE_URL,
    XueqiuAuth,
    XueqiuAuthError,
    _parse_cookie_string,
)


# ---------------------------------------------------------------------------
# Cookie parsing / auth
# ---------------------------------------------------------------------------


class TestParseCookieString:
    def test_empty(self):
        assert _parse_cookie_string("") == {}

    def test_simple(self):
        assert _parse_cookie_string("xq_a_token=abc123") == {"xq_a_token": "abc123"}

    def test_full_xueqiu_cookie(self):
        raw = "xq_a_token=abc123; u=1234567890; device_id=DEADBEEF"
        parsed = _parse_cookie_string(raw)
        assert parsed == {
            "xq_a_token": "abc123",
            "u": "1234567890",
            "device_id": "DEADBEEF",
        }

    def test_extra_whitespace(self):
        raw = "  xq_a_token = abc ;   u=42 ; "
        parsed = _parse_cookie_string(raw)
        assert parsed == {"xq_a_token": "abc", "u": "42"}

    def test_dup_keys_last_wins(self):
        raw = "xq_a_token=first; xq_a_token=second"
        assert _parse_cookie_string(raw) == {"xq_a_token": "second"}

    def test_skips_chunks_without_equals(self):
        raw = "xq_a_token=abc; standalone; u=42"
        assert _parse_cookie_string(raw) == {"xq_a_token": "abc", "u": "42"}


class TestXueqiuAuth:
    def test_construct_without_cookie_raises(self, monkeypatch):
        monkeypatch.delenv("XUEQIU_COOKIE", raising=False)
        with pytest.raises(XueqiuAuthError) as exc:
            XueqiuAuth()
        assert "XUEQIU_COOKIE" in str(exc.value)

    def test_construct_with_short_token_raises(self):
        with pytest.raises(XueqiuAuthError):
            XueqiuAuth(cookie="xq_a_token=ab")

    def test_construct_with_explicit_cookie(self, monkeypatch):
        monkeypatch.delenv("XUEQIU_COOKIE", raising=False)
        auth = XueqiuAuth(cookie="xq_a_token=abcdef1234; u=99; device_id=z")
        assert auth.has_cookie
        assert auth.cookie_header.startswith("xq_a_token=abcdef1234")

    def test_construct_from_env(self, monkeypatch):
        monkeypatch.setenv("XUEQIU_COOKIE", "xq_a_token=envtoken; u=1; device_id=d")
        auth = XueqiuAuth()
        assert auth.has_cookie
        assert auth._cookies["xq_a_token"] == "envtoken"

    @pytest.mark.asyncio
    async def test_is_valid_returns_false_on_5xx(self, monkeypatch):
        auth = XueqiuAuth(cookie="xq_a_token=abc123def; u=1; device_id=d")

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="upstream busy")

        transport = httpx.MockTransport(handler)
        with patch("app.services.news.sources.xueqiu_auth.make_client") as mc:
            cm = _FakeAsyncClientCM(transport)
            mc.return_value = cm
            ok = await auth.is_valid(force=True)
        assert ok is False

    @pytest.mark.asyncio
    async def test_is_valid_returns_true_on_proper_payload(self):
        auth = XueqiuAuth(cookie="xq_a_token=abc123def; u=1; device_id=d")

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"list": [], "error_code": "0"})

        transport = httpx.MockTransport(handler)
        with patch("app.services.news.sources.xueqiu_auth.make_client") as mc:
            mc.return_value = _FakeAsyncClientCM(transport)
            ok = await auth.is_valid(force=True)
        assert ok is True

    @pytest.mark.asyncio
    async def test_is_valid_caches_for_five_minutes(self):
        auth = XueqiuAuth(cookie="xq_a_token=abc123def; u=1; device_id=d")
        auth._probe_ok = True
        auth._probed_at = _now_ts()
        # No transport patch needed; should hit the cache and return True.
        assert await auth.is_valid() is True


class _FakeAsyncClientCM:
    """Tiny async context-manager that yields an httpx.AsyncClient backed
    by the supplied MockTransport. Lets us patch ``make_client`` cheaply.

    A new client is created on every ``__aenter__`` so multiple sequential
    ``async with`` calls in a single test don't trip the
    "client already closed" guard.
    """

    def __init__(self, transport: httpx.MockTransport) -> None:
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> httpx.AsyncClient:
        self._client = httpx.AsyncClient(transport=self._transport, timeout=5.0)
        return self._client

    async def __aexit__(self, *exc) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def _now_ts() -> float:
    # datetime.timestamp on aware datetimes uses the platform's UTC
    # implementation; we just need a relative comparison so the float
    # is fine.
    return datetime.now(tz=timezone.utc).timestamp()


# ---------------------------------------------------------------------------
# Time / symbol helpers
# ---------------------------------------------------------------------------


class TestParseXueqiuTime:
    def test_epoch_millis_int(self):
        ts = 1_700_000_000_000
        out = _parse_xueqiu_time(ts)
        assert out is not None
        assert out.tzinfo is not None
        assert int(out.timestamp() * 1000) == ts

    def test_epoch_millis_string(self):
        out = _parse_xueqiu_time("1700000000000")
        assert out is not None
        assert out.tzinfo is not None

    def test_iso_string(self):
        out = _parse_xueqiu_time("2024-01-02T03:04:05Z")
        assert out is not None
        assert out.tzinfo is not None
        assert out.year == 2024 and out.hour == 3

    def test_none(self):
        assert _parse_xueqiu_time(None) is None

    def test_garbage(self):
        assert _parse_xueqiu_time("not-a-date") is None


class TestToXueqiuSymbol:
    def test_a_share_sh(self):
        assert to_xueqiu_symbol("600519.SH") == "SH600519"

    def test_a_share_sz(self):
        assert to_xueqiu_symbol("000001.SZ") == "SZ000001"

    def test_us(self):
        assert to_xueqiu_symbol("AAPL.US") == "AAPL"

    def test_hk_pads_to_five(self):
        assert to_xueqiu_symbol("0700.HK") == "HK00700"

    def test_already_native_form(self):
        assert to_xueqiu_symbol("SH600519") == "SH600519"

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            to_xueqiu_symbol("")


class TestExtractSymbols:
    def test_cashtags(self):
        post = {"description": "看好 $SH600519$ 和 $AAPL$ 的走势"}
        assert "600519.SH" in extract_symbols(post)
        assert "AAPL.US" in extract_symbols(post)

    def test_hk_cashtag(self):
        post = {"description": "$HK00700$ 终于回调"}
        symbols = extract_symbols(post)
        assert "00700.HK" in symbols

    def test_no_tickers(self):
        assert extract_symbols("今天市场很平静") == []

    def test_post_dict(self):
        post = {
            "title": "$TSLA$ 财报超预期",
            "description": "$AAPL$ 也不错",
        }
        symbols = extract_symbols(post)
        assert "TSLA.US" in symbols
        assert "AAPL.US" in symbols


# ---------------------------------------------------------------------------
# Timeline parsing
# ---------------------------------------------------------------------------


def _timeline_payload() -> dict[str, Any]:
    return {
        "list": [
            {
                "id": 100,
                "title": "茅台新高",
                "description": "看好 $SH600519$ 后续走势",
                "created_at": 1_700_000_000_000,
                "like_count": 5,
                "reply_count": 2,
                "retweet_count": 1,
                "view_count": 1000,
                "user": {
                    "id": 42,
                    "screen_name": "alpha_hunter",
                    "followers_count": 12345,
                },
            },
            {
                "id": 101,
                "description": "震荡行情观望",
                "created_at": 1_699_999_000_000,
                "like_count": 0,
                "reply_count": 0,
                "retweet_count": 0,
                "view_count": 0,
                "user": {"id": 43, "screen_name": "anon", "followers_count": 10},
            },
        ]
    }


class TestXueqiuCrawlerParsing:
    def test_parse_timeline_extracts_engagement_and_symbols(self):
        crawler = XueqiuCrawler(auth=XueqiuAuth(cookie="xq_a_token=validtoken; u=1; device_id=d"))
        posts = crawler._parse_timeline(_timeline_payload(), primary_symbol="600519.SH")
        assert len(posts) == 2
        first = posts[0]
        assert first.source_id == "100"
        assert first.url == "https://xueqiu.com/100"
        assert first.author == "alpha_hunter"
        assert first.author_id == 42
        assert first.author_followers == 12345
        assert first.engagement == {
            "likes": 5,
            "comments": 2,
            "reposts": 1,
            "views": 1000,
        }
        assert "600519.SH" in first.symbols

    def test_parse_timeline_primary_symbol_added(self):
        crawler = XueqiuCrawler(auth=XueqiuAuth(cookie="xq_a_token=validtoken; u=1; device_id=d"))
        posts = crawler._parse_timeline(_timeline_payload(), primary_symbol="AAPL.US")
        # First post mentioned $SH600519$ but primary was AAPL.US; both
        # should now appear in the post's symbols.
        assert "AAPL.US" in posts[0].symbols
        assert "600519.SH" in posts[0].symbols

    def test_parse_timeline_skips_non_dict_items(self):
        payload = {"list": ["junk", {"id": 1, "description": "x", "user": {}, "created_at": 0}]}
        crawler = XueqiuCrawler(auth=XueqiuAuth(cookie="xq_a_token=validtoken; u=1; device_id=d"))
        out = crawler._parse_timeline(payload, primary_symbol="000001.SZ")
        assert len(out) == 1

    def test_normalised_post_to_article(self):
        crawler = XueqiuCrawler(auth=XueqiuAuth(cookie="xq_a_token=validtoken; u=1; device_id=d"))
        posts = crawler._parse_timeline(_timeline_payload(), primary_symbol="600519.SH")
        article = posts[0].to_article()
        assert isinstance(article, RawArticle)
        assert article.source == "xueqiu"
        assert article.source_id == "100"
        assert article.engagement["likes"] == 5
        assert article.extra["author_id"] == 42

    def test_parse_timeline_handles_nested_public_timeline(self):
        """public_timeline.json wraps posts in category buckets with a 'data' string."""
        payload = {
            "list": [
                {
                    "category": 0,
                    "column": "今日话题",
                    "list": [
                        {
                            "id": 20396091,
                            "category": 0,
                            "data": json.dumps(
                                {
                                    "id": 398326989,
                                    "title": "茅台新高",
                                    "description": "看好 $SH600519$ 后续走势",
                                    "created_at": 1_700_000_000_000,
                                    "like_count": 5,
                                    "reply_count": 2,
                                    "retweet_count": 1,
                                    "view_count": 1000,
                                    "user": {
                                        "id": 42,
                                        "screen_name": "alpha_hunter",
                                        "followers_count": 12345,
                                    },
                                }
                            ),
                        }
                    ],
                }
            ]
        }
        crawler = XueqiuCrawler(auth=XueqiuAuth(cookie="xq_a_token=validtoken; u=1; device_id=d"))
        posts = crawler._parse_timeline(payload, primary_symbol="600519.SH")
        assert len(posts) == 1
        assert posts[0].source_id == "398326989"
        assert posts[0].title == "茅台新高"
        assert posts[0].author == "alpha_hunter"
        assert "600519.SH" in posts[0].symbols


# ---------------------------------------------------------------------------
# Incremental cursor (last_max_id)
# ---------------------------------------------------------------------------


class TestIncrementalCursor:
    @pytest.mark.asyncio
    async def test_last_max_id_advances_between_pages(self):
        """The cursor returned by a page should be the oldest id on that page."""
        # First page: ids 200..210 (descending), oldest = 200
        # Second page: ids 190..200 (older), oldest = 190
        page_a = {
            "list": [
                {"id": 210, "description": "x", "user": {}, "created_at": 0},
                {"id": 205, "description": "x", "user": {}, "created_at": 0},
                {"id": 200, "description": "x", "user": {}, "created_at": 0},
            ]
        }
        page_b = {
            "list": [
                {"id": 200, "description": "x", "user": {}, "created_at": 0},
                {"id": 195, "description": "x", "user": {}, "created_at": 0},
                {"id": 190, "description": "x", "user": {}, "created_at": 0},
            ]
        }

        responses = iter([page_a, page_b])
        seen_urls: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen_urls.append(str(request.url))
            return httpx.Response(200, json=next(responses))

        transport = httpx.MockTransport(handler)
        with patch("app.services.news.sources.xueqiu.make_client") as mc:
            mc.return_value = _FakeAsyncClientCM(transport)
            crawler = XueqiuCrawler(
                auth=XueqiuAuth(cookie="xq_a_token=validtoken; u=1; device_id=d"),
                per_minute=1000,  # speed up the test
            )
            posts_a = await crawler.fetch_symbol("600519.SH")
            oldest_a = int(posts_a[-1].source_id)
            assert oldest_a == 200

            posts_b = await crawler.fetch_symbol("600519.SH")
            oldest_b = int(posts_b[-1].source_id)
            assert oldest_b == 190

        # Both requests hit the timeline URL.
        assert all("/v4/statuses/public_timeline.json" in u for u in seen_urls)


# ---------------------------------------------------------------------------
# Network error handling
# ---------------------------------------------------------------------------


class TestNetworkErrors:
    @pytest.mark.asyncio
    async def test_5xx_returns_none(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(502, text="bad gateway")

        transport = httpx.MockTransport(handler)
        with patch("app.services.news.sources.xueqiu.make_client") as mc:
            mc.return_value = _FakeAsyncClientCM(transport)
            crawler = XueqiuCrawler(
                auth=XueqiuAuth(cookie="xq_a_token=validtoken; u=1; device_id=d"),
                per_minute=1000,
            )
            result = await crawler.fetch_post_detail(123)
        assert result is None

    @pytest.mark.asyncio
    async def test_429_eventually_returns_none(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "0"}, text="rate-limited")

        transport = httpx.MockTransport(handler)
        with patch("app.services.news.sources.xueqiu.make_client") as mc:
            mc.return_value = _FakeAsyncClientCM(transport)
            crawler = XueqiuCrawler(
                auth=XueqiuAuth(cookie="xq_a_token=validtoken; u=1; device_id=d"),
                per_minute=1000,
            )
            result = await crawler.fetch_post_detail(123)
        assert result is None

    @pytest.mark.asyncio
    async def test_401_raises_auth_error(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="unauthorized")

        transport = httpx.MockTransport(handler)
        auth = XueqiuAuth(cookie="xq_a_token=validtoken; u=1; device_id=d")
        with patch("app.services.news.sources.xueqiu.make_client") as mc:
            mc.return_value = _FakeAsyncClientCM(transport)
            crawler = XueqiuCrawler(auth=auth, per_minute=1000)
            with pytest.raises(XueqiuAuthError):
                await crawler.fetch_post_detail(123)

    @pytest.mark.asyncio
    async def test_non_json_returns_none(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>oops</html>")

        transport = httpx.MockTransport(handler)
        with patch("app.services.news.sources.xueqiu.make_client") as mc:
            mc.return_value = _FakeAsyncClientCM(transport)
            crawler = XueqiuCrawler(
                auth=XueqiuAuth(cookie="xq_a_token=validtoken; u=1; device_id=d"),
                per_minute=1000,
            )
            result = await crawler.fetch_post_detail(123)
        assert result is None
