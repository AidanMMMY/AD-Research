"""Tests for the WeChat (wewe-rss) crawler and the marketing filter.

Crawler tests are pure-unit — no network. They build an
``httpx.MockTransport`` that returns canned wewe-rss JSON, mirroring
the response shape wewe-rss ships today.

Marketing filter tests cover the heuristic blocklist path, the LLM
reclassify path (with a stubbed provider), and the fail-open behaviour.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from app.services.news.crawler.types import RawArticle
from app.services.news.filters.wechat_marketing_filter import (
    DEFAULT_MARKETING_KEYWORDS,
    WechatMarketingFilter,
)
from app.services.news.sources.wechat_zeping import (
    WechatZepingCrawler,
    _build_feed_url,
    _item_to_raw_article,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wewe_rss_payload(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap a list of items in the canonical wewe-rss JSON envelope."""
    return {
        "status": "ok",
        "feed": {"title": "泽平宏观"},
        "items": items,
    }


def _wewe_rss_item(
    *,
    title: str = "央行降准 0.5 个百分点解读",
    url: str = "https://mp.weixin.qq.com/s/abc",
    description: str = "中国人民银行决定...",
    content_html: str | None = None,
    date_published: str = "2026-07-01T12:34:56Z",
    authors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": url,
        "title": title,
        "url": url,
        "description": description,
        "date_published": date_published,
    }
    if content_html is not None:
        item["content_html"] = content_html
    if authors is not None:
        item["authors"] = authors
    return item


class _StubLLMProvider:
    """Minimal stand-in for :class:`DeepSeekProvider`.

    Returns a pre-canned JSON string from :meth:`complete` and
    ``is_available=True``. Tests build an instance with a
    ``complete_return`` / ``complete_side_effect``.
    """

    def __init__(
        self,
        *,
        complete_return: str = '{"knowledge": true, "confidence": 0.9}',
        complete_side_effect: Exception | None = None,
        is_available: bool = True,
    ) -> None:
        self._complete_return = complete_return
        self._side_effect = complete_side_effect
        self._is_available = is_available
        self.calls: list[dict[str, Any]] = []

    @property
    def is_available(self) -> bool:
        return self._is_available

    def complete(self, prompt: str, system: str | None = None, **_: Any) -> str:
        self.calls.append({"prompt": prompt, "system": system})
        if self._side_effect is not None:
            raise self._side_effect
        return self._complete_return


def _make_mock_client(handler) -> httpx.AsyncClient:
    """Build an ``httpx.AsyncClient`` whose transport is ``handler``."""
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, timeout=5.0)


def _ok_handler(payload: dict[str, Any]):
    """Build a transport handler that returns ``payload`` as JSON."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return _handler


def _status_handler(status: int, body: str = ""):
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=body)

    return _handler


# ---------------------------------------------------------------------------
# URL builder
# ---------------------------------------------------------------------------


class TestFeedUrl:
    def test_trailing_slash_on_base_stripped(self):
        url = _build_feed_url("http://localhost:4000/", "MP_WXS_123", 25)
        assert url == "http://localhost:4000/feeds/MP_WXS_123.json?limit=25"

    def test_no_trailing_slash(self):
        url = _build_feed_url("http://localhost:4000", "abc", 10)
        assert url == "http://localhost:4000/feeds/abc.json?limit=10"


# ---------------------------------------------------------------------------
# Item parser (pure function, no I/O)
# ---------------------------------------------------------------------------


class TestItemParser:
    def test_happy_path(self):
        item = _wewe_rss_item()
        art = _item_to_raw_article(item, feed_id="MP_WXS_123")
        assert art is not None
        assert art.source == "wechat_zeping"
        assert art.url == "https://mp.weixin.qq.com/s/abc"
        assert "央行" in art.title
        assert art.body == "中国人民银行决定..."
        assert art.language == "zh"
        assert art.market == "cn_a"
        assert art.extra["feed_id"] == "MP_WXS_123"
        # ``date_published`` is ISO Z → UTC.
        assert art.published_at.tzinfo is not None
        assert art.published_at.year == 2026

    def test_missing_title_returns_none(self):
        item = _wewe_rss_item(title="")
        assert _item_to_raw_article(item, feed_id="f") is None

    def test_missing_url_returns_none(self):
        item = _wewe_rss_item(url="")
        assert _item_to_raw_article(item, feed_id="f") is None

    def test_authors_normalized_to_csv(self):
        item = _wewe_rss_item(
            authors=[{"name": "任泽平"}, {"name": "团队"}],
        )
        art = _item_to_raw_article(item, feed_id="f")
        assert art is not None
        assert art.author == "任泽平, 团队"

    def test_description_falls_back_to_html_stripped_text(self):
        item = _wewe_rss_item(
            description="",
            content_html="<p>宏观分析：央行降准 0.5 个百分点</p>",
        )
        art = _item_to_raw_article(item, feed_id="f")
        assert art is not None
        assert art.body is not None and "<" not in art.body
        assert "宏观分析" in art.body

    def test_unix_timestamp_date_accepted(self):
        item = _wewe_rss_item(date_published=1720051200)  # 2024-07-04T00:00:00Z
        art = _item_to_raw_article(item, feed_id="f")
        assert art is not None
        assert art.published_at.tzinfo is not None

    def test_garbage_date_falls_back_to_now(self):
        item = _wewe_rss_item(date_published="not a date")
        art = _item_to_raw_article(item, feed_id="f")
        assert art is not None
        # Falls back to now (within the last few seconds).
        delta = abs((datetime.now(tz=timezone.utc) - art.published_at).total_seconds())
        assert delta < 5


# ---------------------------------------------------------------------------
# Crawler integration (httpx mocked)
# ---------------------------------------------------------------------------


class TestCrawlerFetch:
    def test_fetch_recent_returns_raw_articles(self):
        payload = _wewe_rss_payload([
            _wewe_rss_item(title="文章1"),
            _wewe_rss_item(
                title="文章2",
                url="https://mp.weixin.qq.com/s/def",
                date_published="2026-07-02T01:02:03Z",
            ),
        ])
        client = _make_mock_client(_ok_handler(payload))
        crawler = WechatZepingCrawler(
            base_url="http://localhost:4000",
            feed_id="MP_WXS_123",
            client=client,
        )
        arts = asyncio.run(crawler.fetch_recent(limit=30))
        assert len(arts) == 2
        assert {a.url for a in arts} == {
            "https://mp.weixin.qq.com/s/abc",
            "https://mp.weixin.qq.com/s/def",
        }

    def test_multiple_feeds_fetched_and_tagged(self):
        received_urls: list[str] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            received_urls.append(str(request.url))
            return httpx.Response(200, json=_wewe_rss_payload([_wewe_rss_item()]))

        client = _make_mock_client(_handler)
        crawler = WechatZepingCrawler(
            base_url="http://localhost:4000",
            feed_id=["MP_WXS_1", "MP_WXS_2"],
            client=client,
        )
        arts = asyncio.run(crawler.fetch_recent())
        assert len(arts) == 2
        assert len(received_urls) == 2
        # Each article is tagged with its originating feed id.
        feed_ids = {a.extra["feed_id"] for a in arts}
        assert feed_ids == {"MP_WXS_1", "MP_WXS_2"}

    def test_server_unreachable_returns_empty_list(self):
        """A down wewe-rss is a silent no-op — no exception bubbles up."""
        def _boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        client = _make_mock_client(_boom)
        crawler = WechatZepingCrawler(
            base_url="http://localhost:4000",
            feed_id="MP_WXS_123",
            client=client,
        )
        # Should not raise.
        arts = asyncio.run(crawler.fetch_recent())
        assert arts == []

    def test_404_is_silent_no_data(self):
        client = _make_mock_client(_status_handler(404))
        crawler = WechatZepingCrawler(
            base_url="http://localhost:4000",
            feed_id="unknown_feed",
            client=client,
        )
        arts = asyncio.run(crawler.fetch_recent())
        assert arts == []

    def test_5xx_falls_through_as_warning(self):
        client = _make_mock_client(_status_handler(503, body="down"))
        crawler = WechatZepingCrawler(
            base_url="http://localhost:4000",
            feed_id="MP_WXS_123",
            client=client,
        )
        arts = asyncio.run(crawler.fetch_recent())
        assert arts == []

    def test_empty_base_url_skips(self):
        crawler = WechatZepingCrawler(base_url="", feed_id="MP_WXS_123")
        arts = asyncio.run(crawler.fetch_recent())
        assert arts == []

    def test_empty_feed_id_skips(self):
        crawler = WechatZepingCrawler(
            base_url="http://localhost:4000", feed_id=""
        )
        arts = asyncio.run(crawler.fetch_recent())
        assert arts == []

    def test_non_json_payload_skipped(self):
        client = _make_mock_client(
            lambda req: httpx.Response(200, text="<html>oops</html>")
        )
        crawler = WechatZepingCrawler(
            base_url="http://localhost:4000",
            feed_id="MP_WXS_123",
            client=client,
        )
        arts = asyncio.run(crawler.fetch_recent())
        assert arts == []

    def test_settings_driven_construction(self, monkeypatch):
        monkeypatch.setenv("WECHAT_RSS_BASE_URL", "http://rss.local:9999")
        monkeypatch.setenv("WECHAT_RSS_FEED_ID", "MP_WXS_A,MP_WXS_B")
        # Need to bust get_settings cache.
        from app.config import get_settings
        get_settings.cache_clear()
        try:
            crawler = WechatZepingCrawler()
            assert crawler._base_url == "http://rss.local:9999"
            assert crawler._feed_ids == ["MP_WXS_A", "MP_WXS_B"]
        finally:
            get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Marketing filter — heuristic
# ---------------------------------------------------------------------------


class TestFilterHeuristic:
    def test_empty_title_is_marketing(self):
        f = WechatMarketingFilter(llm_enabled=False)
        verdict = f.classify("", "任何内容")
        assert verdict.is_knowledge is False
        assert verdict.reason == "empty_input"

    def test_known_marketing_keyword_rejected(self):
        f = WechatMarketingFilter(llm_enabled=False)
        verdict = f.classify(
            "重磅预告：泽平宏观研学计划开启报名",
            "扫码加入即送内部资料，名额有限",
        )
        assert verdict.is_knowledge is False
        assert verdict.reason == "keyword_blocklist"

    def test_global_wealth_meeting_rejected(self):
        f = WechatMarketingFilter(llm_enabled=False)
        verdict = f.classify(
            "全球财富会盛大开幕", "席位预定请扫码"
        )
        assert verdict.is_knowledge is False
        assert verdict.reason == "keyword_blocklist"

    def test_knowledge_title_passes_heuristic(self):
        f = WechatMarketingFilter(llm_enabled=False)
        verdict = f.classify(
            "央行降准 0.5 个百分点：宏观流动性分析",
            "中国人民银行决定下调存款准备金率。本文从宏观流动性和利率"
            "传导两个角度展开分析。",
        )
        # Without the LLM, knowledge content is treated as knowledge.
        assert verdict.is_knowledge is True
        assert verdict.reason == "llm_disabled_knowledge"

    def test_marketing_keyword_in_body_only_also_rejected(self):
        f = WechatMarketingFilter(llm_enabled=False)
        verdict = f.classify(
            "本周宏观观点",
            "本周市场观点：关注通胀拐点。泽平宏观研学计划开启报名，"
            "请扫码加入。",
        )
        assert verdict.is_knowledge is False
        assert verdict.reason == "keyword_blocklist"


# ---------------------------------------------------------------------------
# Marketing filter — LLM path
# ---------------------------------------------------------------------------


class TestFilterLlm:
    def test_llm_says_knowledge(self):
        provider = _StubLLMProvider(
            complete_return='{"knowledge": true, "confidence": 0.92}'
        )
        f = WechatMarketingFilter(llm_provider=provider)
        verdict = f.classify(
            "央行降准解读：宏观流动性分析", "中国人民银行..."
        )
        assert verdict.is_knowledge is True
        assert verdict.reason == "llm_knowledge"
        assert verdict.confidence == pytest.approx(0.92, abs=1e-6)
        # Provider was actually called.
        assert len(provider.calls) == 1

    def test_llm_says_marketing(self):
        provider = _StubLLMProvider(
            complete_return='{"knowledge": false, "confidence": 0.88}'
        )
        f = WechatMarketingFilter(llm_provider=provider)
        # Body deliberately avoids the heuristic keywords so the LLM
        # path is the one under test.
        verdict = f.classify(
            "本周宏观观点速递",
            "对通胀、利率、汇率三个变量的最新看法。本文为作者原创分析。",
        )
        assert verdict.is_knowledge is False
        assert verdict.reason == "llm_marketing"
        assert verdict.confidence == pytest.approx(0.88, abs=1e-6)

    def test_llm_error_falls_open_to_knowledge(self):
        provider = _StubLLMProvider(complete_side_effect=RuntimeError("timeout"))
        f = WechatMarketingFilter(llm_provider=provider)
        verdict = f.classify("宏观分析", "正文")
        assert verdict.is_knowledge is True
        assert verdict.reason == "llm_error_fallthrough"

    def test_llm_unavailable_falls_open(self):
        provider = _StubLLMProvider(is_available=False)
        f = WechatMarketingFilter(llm_provider=provider)
        verdict = f.classify("宏观分析", "正文")
        assert verdict.is_knowledge is True
        assert verdict.reason == "llm_unavailable_fallthrough"

    def test_keyword_blocklist_short_circuits_before_llm(self):
        """Heuristic match should never call the LLM."""
        provider = _StubLLMProvider(
            complete_return='{"knowledge": true, "confidence": 0.99}'
        )
        f = WechatMarketingFilter(llm_provider=provider)
        verdict = f.classify("研学计划开启报名", "扫码加入")
        assert verdict.is_knowledge is False
        assert verdict.reason == "keyword_blocklist"
        assert provider.calls == []  # LLM never invoked.

    def test_malformed_json_falls_open(self):
        provider = _StubLLMProvider(complete_return="I'm not JSON at all")
        f = WechatMarketingFilter(llm_provider=provider)
        verdict = f.classify("宏观分析", "正文")
        # Unparseable → fall through (keep article).
        assert verdict.is_knowledge is True
        assert verdict.reason == "llm_parse_error_fallthrough"

    def test_markdown_fenced_json_parses(self):
        provider = _StubLLMProvider(
            complete_return='```json\n{"knowledge": true, "confidence": 0.7}\n```'
        )
        f = WechatMarketingFilter(llm_provider=provider)
        verdict = f.classify("宏观分析", "正文")
        assert verdict.is_knowledge is True
        assert verdict.confidence == pytest.approx(0.7, abs=1e-6)

    def test_string_typed_knowledge(self):
        provider = _StubLLMProvider(
            complete_return='{"knowledge": "false", "confidence": 0.6}'
        )
        f = WechatMarketingFilter(llm_provider=provider)
        verdict = f.classify("某标题", "某正文")
        assert verdict.is_knowledge is False
        assert verdict.reason == "llm_marketing"

    def test_llm_result_is_cached(self):
        provider = _StubLLMProvider(
            complete_return='{"knowledge": true, "confidence": 0.9}'
        )
        f = WechatMarketingFilter(llm_provider=provider, cache_ttl_seconds=3600)
        title = "央行降准解读"
        body = "中国人民银行决定..."
        v1 = f.classify(title, body)
        v2 = f.classify(title, body)
        assert v1.is_knowledge is True
        assert v2.is_knowledge is True
        # The second call should hit the cache, not the LLM.
        assert len(provider.calls) == 1


# ---------------------------------------------------------------------------
# Marketing filter — default keyword surface
# ---------------------------------------------------------------------------


class TestDefaultKeywords:
    def test_keywords_not_empty(self):
        assert len(DEFAULT_MARKETING_KEYWORDS) >= 10

    @pytest.mark.parametrize("keyword", [
        "研学计划", "课程报名", "直播预告", "全球财富会",
        "扫码加入", "席位预定", "早鸟价", "邀请函",
        "知识星球", "免费领取", "内部活动", "私享会",
    ])
    def test_default_keyword_catches_example(self, keyword):
        f = WechatMarketingFilter(llm_enabled=False)
        verdict = f.classify(f"标题包含{keyword}", "正文")
        assert verdict.is_knowledge is False, f"keyword {keyword!r} missed"
        assert verdict.reason == "keyword_blocklist"