"""Tests for the independent non-WeChat batch crawler (2026-07-28).

Covers:
  - The feed table obeys the independence selection rule (no official
    media / corporate-PR sources) and has unique slugs/URLs.
  - Batches partition the table completely.
  - ``IndependentBatchCrawler`` parses feeds into per-source articles
    with a mocked HTTP layer, honouring per-row market/language.
  - Batch jobs materialize in ``scheduler_jobs`` and are wired into
    the health-grid metadata.
"""

from __future__ import annotations

import asyncio
import re

import httpx
import pytest

from app.services.news.sources.independent_batch import (
    INDEPENDENT_BATCHES,
    INDEPENDENT_FEEDS,
    IndependentBatchCrawler,
)

# Names that must never appear in the table — official media or
# corporate PR channels (user requirement: independent voices only).
_FORBIDDEN = (
    "人民日报", "新华社", "央视", "证券时", "官方", "第一财经",
    "Bloomberg", "Reuters", "CNBC",
)

_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>{name}</title>
    <item>
      <title>本周市场复盘</title>
      <link>https://example.com/post-1</link>
      <description>&lt;p&gt;摘要一段。&lt;/p&gt;</description>
      <pubDate>Sun, 26 Jul 2026 22:47:18 +0800</pubDate>
    </item>
  </channel>
</rss>"""

_BATCH_KEYS = list(INDEPENDENT_BATCHES.keys())


class TestFeedTable:
    def test_unique_slugs_and_urls(self):
        slugs = [s for s, *_ in INDEPENDENT_FEEDS]
        urls = [u for _, _, u, _, _ in INDEPENDENT_FEEDS]
        assert len(slugs) == len(set(slugs))
        assert len(urls) == len(set(urls))

    def test_slug_format(self):
        for s, *_ in INDEPENDENT_FEEDS:
            assert re.fullmatch(r"[a-z0-9]+", s), f"bad slug {s}"

    def test_no_official_or_pr_sources(self):
        for _, name, *_ in INDEPENDENT_FEEDS:
            for bad in _FORBIDDEN:
                assert bad not in name, f"{name} looks official/PR"

    def test_market_and_language_values(self):
        for _, _, _, market, lang in INDEPENDENT_FEEDS:
            assert market in {"cn_a", "us", "crypto"}
            assert lang in {"zh", "en"}

    def test_https_except_known_http_hosts(self):
        # 喜马拉雅 / 荔枝 album feeds only serve plain HTTP.
        allowed_http = ("www.ximalaya.com", "rss.lizhi.fm", "wjd.name",
                        "www.gtdstudy.com", "blog.trumandu.top")
        for _, _, url, _, _ in INDEPENDENT_FEEDS:
            if url.startswith("https://"):
                continue
            assert url.startswith("http://")
            host = url.removeprefix("http://").split("/")[0]
            assert host in allowed_http, f"unexpected http host {host}"

    def test_batches_partition_table(self):
        flat = [row for batch in INDEPENDENT_BATCHES.values() for row in batch]
        assert flat == INDEPENDENT_FEEDS

    def test_at_least_100_sources(self):
        assert len(INDEPENDENT_FEEDS) >= 100

    def test_no_overlap_with_wechat2rss_table(self):
        from app.services.news.sources.wechat2rss_batch import WECHAT2RSS_FEEDS

        wechat_names = {n for _, n, _ in WECHAT2RSS_FEEDS}
        for _, name, *_ in INDEPENDENT_FEEDS:
            assert name not in wechat_names


class TestBatchCrawler:
    def _client(self) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_SAMPLE.format(name="测试源"))

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def test_fetch_recent_maps_per_feed_source(self):
        crawler = IndependentBatchCrawler("a", delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        expected = {f"indie_{s}" for s, *_ in INDEPENDENT_BATCHES["a"]}
        assert {a.source for a in articles} == expected
        market_by_slug = {s: m for s, _, _, m, _ in INDEPENDENT_BATCHES["a"]}
        lang_by_slug = {s: lang for s, _, _, _, lang in INDEPENDENT_BATCHES["a"]}
        for a in articles:
            slug = a.source.removeprefix("indie_")
            assert a.market == market_by_slug[slug]
            assert a.language == lang_by_slug[slug]
            assert "摘要一段" in (a.body or "")

    def test_unknown_batch_is_empty_not_error(self):
        crawler = IndependentBatchCrawler("zzz", delay_seconds=0, client=self._client())
        assert asyncio.run(crawler.fetch_recent()) == []

    def test_failing_feed_does_not_break_batch(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = IndependentBatchCrawler("a", delay_seconds=0, client=client)
        assert asyncio.run(crawler.fetch_recent()) == []


class TestSchedulerWiring:
    def test_batch_jobs_materialized(self):
        from app.services.news import scheduler_jobs as sj

        for job_id, _label, batch in sj.INDEPENDENT_BATCH_JOBS:
            fn = getattr(sj, f"run_independent_{batch}_crawl")
            assert callable(fn)
            assert fn.__name__ == f"run_independent_{batch}_crawl"

    def test_job_table_covers_all_batches(self):
        from app.services.news import scheduler_jobs as sj

        assert {b for _, _, b in sj.INDEPENDENT_BATCH_JOBS} == set(_BATCH_KEYS)

    @pytest.mark.parametrize("batch", _BATCH_KEYS)
    def test_health_meta_exists(self, batch):
        from app.api.v1.news import _WORKER_META

        assert f"news_indie_{batch}_60m" in _WORKER_META

    def test_health_keyword_covers_job_ids(self):
        from app.api.v1.news import _WORKER_KEYWORDS

        assert any(k in "news_indie_a_60m" for k in _WORKER_KEYWORDS)
