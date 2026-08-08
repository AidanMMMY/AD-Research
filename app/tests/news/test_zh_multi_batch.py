"""Tests for the Chinese podcast batch crawler (2026-07-29).

Covers:
  - The feed table obeys the selection rule (no official media /
    corporate-brand PR / pure-news shows) and has unique slugs/URLs,
    with zero overlap against every earlier expansion wave
    (``indie_*`` / ``global_*`` / ``gind_*`` / ``asen_*`` / wechat2rss).
  - Batches partition the table completely into <=10-feed groups keyed
    ``a``–``d`` (the ``news_zhx_*`` job namespace is unique, so keys
    restart at ``a``).
  - ``ZhMultiBatchCrawler`` parses feeds into per-source articles with
    a mocked HTTP layer, honouring per-row market/language.

Scheduler-wiring tests (``scheduler_jobs.ZH_MULTI_BATCH_JOBS``
materialization and ``_WORKER_META`` health-grid entries) are skipped
until the integration patch lands — see
``docs/dev-notes/20260729-zh-multi-batch-integration.md``.
"""

from __future__ import annotations

import asyncio
import re

import httpx
import pytest

from app.services.news.sources.zh_multi_batch import (
    ZH_MULTI_BATCH_JOBS,
    ZH_MULTI_BATCHES,
    ZH_MULTI_FEEDS,
    ZhMultiBatchCrawler,
)

# Names that must never appear in the table — official media or
# corporate-brand PR channels (user requirement: independent voices
# only). 商业就是这样 (第一财经杂志), 厚雪长波 (雪球) and 创业内幕
# (纪源资本) were rejected during verification for exactly this reason.
_FORBIDDEN = (
    "人民日报", "新华社", "央视", "证券时", "官方", "第一财经",
    "证券", "基金", "银行", "资本", "集团", "研究所",
)

_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>{name}</title>
    <item>
      <title>E42 深度对谈：周期与配置</title>
      <link>https://example.com/ep-42</link>
      <description>&lt;p&gt;本期 shownotes 正文，含时间轴与嘉宾观点。&lt;/p&gt;</description>
      <enclosure url="https://example.com/ep-42.mp3" length="123456" type="audio/mpeg"/>
      <itunes:duration>3600</itunes:duration>
      <pubDate>Sun, 26 Jul 2026 22:47:18 +0000</pubDate>
    </item>
  </channel>
</rss>"""

_BATCH_KEYS = list(ZH_MULTI_BATCHES.keys())


class TestFeedTable:
    def test_unique_slugs_and_urls(self):
        slugs = [s for s, *_ in ZH_MULTI_FEEDS]
        urls = [u for _, _, u, _, _ in ZH_MULTI_FEEDS]
        assert len(slugs) == len(set(slugs))
        assert len(urls) == len(set(urls))

    def test_slug_format(self):
        for s, *_ in ZH_MULTI_FEEDS:
            assert re.fullmatch(r"[a-z0-9]+", s), f"bad slug {s}"

    def test_no_official_or_pr_sources(self):
        for _, name, *_ in ZH_MULTI_FEEDS:
            for bad in _FORBIDDEN:
                assert bad not in name, f"{name} looks official/PR"

    def test_market_and_language_values(self):
        # Chinese-language wave; market must stay inside the news API's
        # _GLOBAL_MARKETS whitelist (cn_a/us/crypto) or articles would
        # be hidden from the frontend's default filter.
        for _, _, _, market, lang in ZH_MULTI_FEEDS:
            assert market == "cn_a"
            assert lang == "zh"

    def test_at_least_30_sources(self):
        assert len(ZH_MULTI_FEEDS) >= 30

    def test_batches_partition_table(self):
        flat = [row for batch in ZH_MULTI_BATCHES.values() for row in batch]
        assert flat == ZH_MULTI_FEEDS

    def test_batch_keys_start_at_a(self):
        # news_zhx_* is its own job namespace, so keys restart at "a".
        assert min(_BATCH_KEYS) == "a"

    def test_batch_size_at_most_10(self):
        for key, batch in ZH_MULTI_BATCHES.items():
            assert 0 < len(batch) <= 10, f"batch {key} has {len(batch)} feeds"

    def test_no_overlap_with_earlier_waves(self):
        from app.services.news.sources.asia_en_batch import ASIA_EN_FEEDS
        from app.services.news.sources.global_indie_batch import GLOBAL_INDIE_FEEDS
        from app.services.news.sources.global_rss_batch import GLOBAL_RSS_FEEDS
        from app.services.news.sources.independent_batch import INDEPENDENT_FEEDS
        from app.services.news.sources.wechat2rss_batch import WECHAT2RSS_FEEDS
        from app.services.news.sources.wechat2rss_batch2 import WECHAT2B_FEEDS

        other_urls = {u for _, _, u, _, _ in INDEPENDENT_FEEDS}
        other_urls |= {u for _, _, u, _, _ in GLOBAL_RSS_FEEDS}
        other_urls |= {u for _, _, u, _, _ in GLOBAL_INDIE_FEEDS}
        other_urls |= {u for _, _, u, _, _ in ASIA_EN_FEEDS}
        # wechat tables carry 3/4-tuples (slug, name, url[, ...]).
        other_urls |= {row[2] for row in WECHAT2RSS_FEEDS}
        other_urls |= {row[2] for row in WECHAT2B_FEEDS}
        other_slugs = {s for s, *_ in INDEPENDENT_FEEDS}
        other_slugs |= {s for s, *_ in GLOBAL_RSS_FEEDS}
        other_slugs |= {s for s, *_ in GLOBAL_INDIE_FEEDS}
        other_slugs |= {s for s, *_ in ASIA_EN_FEEDS}
        other_slugs |= {row[0] for row in WECHAT2RSS_FEEDS}
        other_slugs |= {row[0] for row in WECHAT2B_FEEDS}
        for slug, _name, url, *_ in ZH_MULTI_FEEDS:
            assert url not in other_urls, f"url already covered: {url}"
            assert slug not in other_slugs, f"slug already used: {slug}"

    def test_batch_jobs_match_batches(self):
        assert {b for _, _, b in ZH_MULTI_BATCH_JOBS} == set(_BATCH_KEYS)
        for job_id, _label, batch in ZH_MULTI_BATCH_JOBS:
            assert job_id == f"news_zhx_{batch}_60m"


class TestBatchCrawler:
    def _client(self) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_SAMPLE.format(name="测试播客"))

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def test_fetch_recent_maps_per_feed_source(self):
        crawler = ZhMultiBatchCrawler("a", delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        expected = {f"zhx_{s}" for s, *_ in ZH_MULTI_BATCHES["a"]}
        assert {a.source for a in articles} == expected
        for a in articles:
            assert a.market == "cn_a"
            assert a.language == "zh"
            assert "shownotes" in (a.body or "")

    def test_podcast_enclosure_ignored_body_from_description(self):
        # <enclosure> / itunes tags need no special handling: the body
        # must come from <description> shownotes.
        crawler = ZhMultiBatchCrawler("a", delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        assert articles
        for a in articles:
            assert a.url == "https://example.com/ep-42"
            assert a.body and "时间轴" in a.body

    def test_unknown_batch_is_empty_not_error(self):
        crawler = ZhMultiBatchCrawler("zzz", delay_seconds=0, client=self._client())
        assert asyncio.run(crawler.fetch_recent()) == []

    def test_failing_feed_does_not_break_batch(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = ZhMultiBatchCrawler("a", delay_seconds=0, client=client)
        assert asyncio.run(crawler.fetch_recent()) == []


class TestSchedulerWiring:
    """The assertions below become active once scheduler_jobs.py,
    core/scheduler.py and api/v1/news.py are updated."""

    def test_batch_jobs_materialized(self):
        from app.services.news import scheduler_jobs as sj

        for _job_id, _label, batch in sj.ZH_MULTI_BATCH_JOBS:
            fn = getattr(sj, f"run_zh_multi_{batch}_crawl")
            assert callable(fn)
            assert fn.__name__ == f"run_zh_multi_{batch}_crawl"

    def test_job_table_covers_all_batches(self):
        from app.services.news import scheduler_jobs as sj

        assert {b for _, _, b in sj.ZH_MULTI_BATCH_JOBS} == set(_BATCH_KEYS)

    @pytest.mark.parametrize("batch", _BATCH_KEYS)
    def test_health_meta_exists(self, batch):
        from app.api.v1.news import _WORKER_META

        assert f"news_zhx_{batch}_60m" in _WORKER_META

    def test_health_keyword_covers_job_ids(self):
        from app.api.v1.news import _WORKER_KEYWORDS

        assert any(k in "news_zhx_a_60m" for k in _WORKER_KEYWORDS)
