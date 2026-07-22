"""Tests for the WeChat multi-feed feed-map support.

Covers ``parse_feed_map`` (well-formed / malformed entries), per-feed
``source`` naming (``wechat_{slug}``), the author fallback to the
display name, ``extra["account_name"]``, and backwards compatibility
when no feed map is configured.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.services.news.sources.wechat_zeping import (
    FeedAccount,
    WechatZepingCrawler,
    _item_to_raw_article,
    parse_feed_map,
)


def _wewe_rss_item(
    *,
    title: str = "央行降准 0.5 个百分点解读",
    url: str = "https://mp.weixin.qq.com/s/abc",
    description: str = "中国人民银行决定...",
    authors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": url,
        "title": title,
        "url": url,
        "description": description,
        "date_published": "2026-07-01T12:34:56Z",
    }
    if authors is not None:
        item["authors"] = authors
    return item


def _make_mock_client(handler) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, timeout=5.0)


# ---------------------------------------------------------------------------
# parse_feed_map
# ---------------------------------------------------------------------------


class TestParseFeedMap:
    def test_empty_and_none(self):
        assert parse_feed_map(None) == {}
        assert parse_feed_map("") == {}
        assert parse_feed_map("   ") == {}

    def test_single_entry(self):
        m = parse_feed_map("MP_WXS_111:zeping:泽平宏观")
        assert m == {"MP_WXS_111": FeedAccount(slug="zeping", display_name="泽平宏观")}

    def test_multiple_entries(self):
        m = parse_feed_map("MP_WXS_111:zeping:泽平宏观, MP_WXS_222:macrowatch:宏观瞭望")
        assert list(m.keys()) == ["MP_WXS_111", "MP_WXS_222"]
        assert m["MP_WXS_222"].slug == "macrowatch"
        assert m["MP_WXS_222"].display_name == "宏观瞭望"

    def test_whitespace_around_fields_tolerated(self):
        m = parse_feed_map(" MP_WXS_111 : zeping : 泽平宏观 ")
        assert m["MP_WXS_111"].display_name == "泽平宏观"

    def test_malformed_entries_skipped(self):
        m = parse_feed_map(
            "good:slug:名字,"
            "two_fields:only,"
            "a:b:c:d,"  # too many fields
            ":slug:noname,"  # empty feed id
            "feed::name,"  # empty slug
            "feed:slug:,"  # empty display name
            ",,"
        )
        assert list(m.keys()) == ["good"]
        assert m["good"] == FeedAccount(slug="slug", display_name="名字")

    def test_chinese_display_name_preserved(self):
        m = parse_feed_map("F:s:任泽平团队（宏观）")
        assert m["F"].display_name == "任泽平团队（宏观）"


# ---------------------------------------------------------------------------
# _item_to_raw_article with account
# ---------------------------------------------------------------------------


class TestItemParserWithAccount:
    def test_mapped_feed_gets_per_feed_source(self):
        account = FeedAccount(slug="zeping", display_name="泽平宏观")
        art = _item_to_raw_article(_wewe_rss_item(), feed_id="MP_WXS_111", account=account)
        assert art is not None
        assert art.source == "wechat_zeping"
        assert art.extra["account_name"] == "泽平宏观"

    def test_author_falls_back_to_display_name(self):
        account = FeedAccount(slug="zeping", display_name="泽平宏观")
        art = _item_to_raw_article(_wewe_rss_item(), feed_id="f", account=account)
        assert art is not None
        assert art.author == "泽平宏观"

    def test_explicit_author_wins_over_display_name(self):
        account = FeedAccount(slug="zeping", display_name="泽平宏观")
        art = _item_to_raw_article(
            _wewe_rss_item(authors=[{"name": "任泽平"}]),
            feed_id="f",
            account=account,
        )
        assert art is not None
        assert art.author == "任泽平"
        # account_name is still tagged for attribution.
        assert art.extra["account_name"] == "泽平宏观"

    def test_unmapped_feed_behaves_like_before(self):
        art = _item_to_raw_article(_wewe_rss_item(), feed_id="f")
        assert art is not None
        assert art.source == "wechat_zeping"
        assert art.author is None
        assert "account_name" not in art.extra


# ---------------------------------------------------------------------------
# Crawler-level feed-map behaviour
# ---------------------------------------------------------------------------


class TestCrawlerFeedMap:
    def test_feed_list_is_union_of_feed_id_and_map(self):
        crawler = WechatZepingCrawler(
            base_url="http://localhost:4000",
            feed_id="MP_WXS_A,MP_WXS_B",
            feed_map="MP_WXS_C:zeping:泽平宏观",
        )
        assert crawler._feed_ids == ["MP_WXS_A", "MP_WXS_B", "MP_WXS_C"]

    def test_map_key_already_in_feed_id_not_duplicated(self):
        crawler = WechatZepingCrawler(
            base_url="http://localhost:4000",
            feed_id="MP_WXS_A",
            feed_map="MP_WXS_A:zeping:泽平宏观",
        )
        assert crawler._feed_ids == ["MP_WXS_A"]

    def test_fetch_recent_tags_mapped_feed_with_per_feed_source(self):
        payload = {"status": "ok", "items": [_wewe_rss_item()]}
        client = _make_mock_client(lambda req: httpx.Response(200, json=payload))
        crawler = WechatZepingCrawler(
            base_url="http://localhost:4000",
            feed_id="MP_WXS_LEGACY",
            feed_map="MP_WXS_111:zeping:泽平宏观",
            client=client,
        )
        arts = asyncio.run(crawler.fetch_recent())
        by_feed = {a.extra["feed_id"]: a for a in arts}
        assert by_feed["MP_WXS_111"].source == "wechat_zeping"
        assert by_feed["MP_WXS_111"].extra["account_name"] == "泽平宏观"
        assert by_feed["MP_WXS_111"].author == "泽平宏观"
        # The unmapped legacy feed is untouched.
        assert by_feed["MP_WXS_LEGACY"].source == "wechat_zeping"
        assert "account_name" not in by_feed["MP_WXS_LEGACY"].extra

    def test_fetch_feed_single_uses_map_too(self):
        payload = {"status": "ok", "items": [_wewe_rss_item()]}
        client = _make_mock_client(lambda req: httpx.Response(200, json=payload))
        crawler = WechatZepingCrawler(
            base_url="http://localhost:4000",
            feed_id="",
            feed_map="MP_WXS_111:zeping:泽平宏观",
            client=client,
        )
        arts = asyncio.run(crawler.fetch_feed("MP_WXS_111"))
        assert len(arts) == 1
        assert arts[0].source == "wechat_zeping"

    def test_no_map_backwards_compatible(self):
        crawler = WechatZepingCrawler(
            base_url="http://localhost:4000",
            feed_id="MP_WXS_A",
            feed_map="",
        )
        assert crawler._feed_map == {}
        assert crawler._feed_ids == ["MP_WXS_A"]

    def test_settings_driven_feed_map(self, monkeypatch):
        monkeypatch.setenv("WECHAT_RSS_BASE_URL", "http://rss.local:9999")
        monkeypatch.setenv("WECHAT_RSS_FEED_ID", "MP_WXS_A")
        monkeypatch.setenv("WECHAT_RSS_FEED_MAP", "MP_WXS_B:zeping:泽平宏观")
        from app.config import get_settings

        get_settings.cache_clear()
        try:
            crawler = WechatZepingCrawler()
            assert crawler._feed_ids == ["MP_WXS_A", "MP_WXS_B"]
            assert crawler._feed_map["MP_WXS_B"].display_name == "泽平宏观"
        finally:
            get_settings.cache_clear()
