"""Tests for the wechat2rss public-mirror batch crawler (2026-07-27).

Covers:
  - The feed table obeys the independence selection rule (no official
    media / corporate-PR accounts) and has unique slugs/hashes.
  - Batches partition the table completely.
  - ``Wechat2RssBatchCrawler`` parses feeds into per-account sources
    with a mocked HTTP layer.
  - Batch jobs materialize in ``scheduler_jobs`` and are registered in
    ``app.core.scheduler``.
"""

from __future__ import annotations

import asyncio
import re

import httpx
import pytest

from app.services.news.sources.wechat2rss_batch import (
    WECHAT2RSS_BATCHES,
    WECHAT2RSS_FEEDS,
    Wechat2RssBatchCrawler,
)

# Names that must never appear in the table — official media or
# corporate PR accounts (user requirement: independent voices only).
_FORBIDDEN = ("人民日报", "新华社", "央视", "证券时", "应急", "官方")

_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>{name}</title>
    <item>
      <title>本周市场复盘</title>
      <link>https://mp.weixin.qq.com/s?__biz=XYZ&amp;mid=1&amp;idx=1&amp;sn=abc</link>
      <description></description>
      <content:encoded><![CDATA[<p>正文内容一段。</p>]]></content:encoded>
      <pubDate>Sun, 26 Jul 2026 22:47:18 +0800</pubDate>
    </item>
  </channel>
</rss>"""


class TestFeedTable:
    def test_unique_slugs_and_hashes(self):
        slugs = [s for s, _, _ in WECHAT2RSS_FEEDS]
        hashes = [h for _, _, h in WECHAT2RSS_FEEDS]
        assert len(slugs) == len(set(slugs))
        assert len(hashes) == len(set(hashes))

    def test_hash_format(self):
        for _, _, h in WECHAT2RSS_FEEDS:
            assert re.fullmatch(r"[0-9a-f]{40}", h)

    def test_no_official_or_pr_accounts(self):
        for _, name, _ in WECHAT2RSS_FEEDS:
            for bad in _FORBIDDEN:
                assert bad not in name, f"{name} looks official/PR"

    def test_batches_partition_table(self):
        flat = [row for batch in WECHAT2RSS_BATCHES.values() for row in batch]
        assert flat == WECHAT2RSS_FEEDS

    def test_at_least_40_accounts(self):
        assert len(WECHAT2RSS_FEEDS) >= 40


class TestBatchCrawler:
    def _client(self) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_SAMPLE.format(name="测试号"))

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def test_fetch_recent_maps_per_feed_source(self):
        crawler = Wechat2RssBatchCrawler("a", delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        expected = {f"wechat_{s}" for s, _, _ in WECHAT2RSS_BATCHES["a"]}
        assert {a.source for a in articles} == expected
        for a in articles:
            assert a.market == "cn_a"
            assert a.language == "zh"
            assert "正文内容" in (a.body or "")

    def test_unknown_batch_is_empty_not_error(self):
        crawler = Wechat2RssBatchCrawler("zzz", delay_seconds=0, client=self._client())
        assert asyncio.run(crawler.fetch_recent()) == []

    def test_failing_feed_does_not_break_batch(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = Wechat2RssBatchCrawler("a", delay_seconds=0, client=client)
        assert asyncio.run(crawler.fetch_recent()) == []


class TestSchedulerWiring:
    def test_batch_jobs_materialized(self):
        from app.services.news import scheduler_jobs as sj

        for _job_id, _label, batch in sj.WECHAT2RSS_BATCH_JOBS:
            fn = getattr(sj, f"run_wechat2rss_{batch}_crawl")
            assert callable(fn)
            assert fn.__name__ == f"run_wechat2rss_{batch}_crawl"

    @pytest.mark.parametrize("batch", ["a", "b", "c", "d", "e", "f", "g", "h", "i"])
    def test_health_meta_exists(self, batch):
        from app.api.v1.news import _WORKER_META

        assert f"news_wechat2rss_{batch}_60m" in _WORKER_META
