"""Tests for the Asia-focused English RSS batch crawler (2026-07-28).

Covers:
  - The feed table is well-formed (unique slugs/URLs, ``asen_`` prefix,
    all-English, known markets, ≥100 feeds — the expansion goal).
  - Batches partition the table completely and ``ASIA_EN_BATCH_JOBS``
    matches the batch geometry.
  - ``AsiaEnBatchCrawler`` parses feeds into per-feed sources with
    per-feed market, with a mocked HTTP layer.
  - No URL overlap with the existing source modules (regression guard
    against double-ingesting a feed another crawler already owns).
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import httpx

from app.services.news.sources.asia_en_batch import (
    ASIA_EN_BATCH_JOBS,
    ASIA_EN_BATCHES,
    ASIA_EN_FEEDS,
    AsiaEnBatchCrawler,
)

_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Sample</title>
    <item>
      <title>Sample headline</title>
      <link>https://example.com/article/1</link>
      <content:encoded><![CDATA[<p>A long English article body about Asian markets, semiconductor supply chains and central-bank policy that runs well past two hundred characters so it counts as a real full text.</p>]]></content:encoded>
      <pubDate>Tue, 28 Jul 2026 08:00:00 +0800</pubDate>
    </item>
  </channel>
</rss>"""


class TestFeedTable:
    def test_unique_slugs_and_urls(self):
        slugs = [r[0] for r in ASIA_EN_FEEDS]
        urls = [r[2] for r in ASIA_EN_FEEDS]
        assert len(slugs) == len(set(slugs))
        assert len(urls) == len(set(urls))

    def test_row_shape_and_values(self):
        valid_markets = {"us", "cn_a", "hk", "crypto", "global"}
        for slug, name, url, market, lang in ASIA_EN_FEEDS:
            assert slug.startswith("asen_")
            assert slug.isascii()
            assert name
            assert url.startswith("https://") or url.startswith("http://")
            assert market in valid_markets
            # This wave is English-only by design; the multilingual
            # wave lives in global_rss_batch.
            assert lang == "en"

    def test_batches_partition_table(self):
        flat = [row for batch in ASIA_EN_BATCHES.values() for row in batch]
        assert flat == ASIA_EN_FEEDS

    def test_batch_sizes(self):
        for key, batch in ASIA_EN_BATCHES.items():
            assert 1 <= len(batch) <= 11, key

    def test_at_least_100_feeds(self):
        assert len(ASIA_EN_FEEDS) >= 100

    def test_jobs_match_batch_geometry(self):
        assert len(ASIA_EN_BATCH_JOBS) == len(ASIA_EN_BATCHES)
        keys = set(ASIA_EN_BATCHES)
        for job_id, label, batch in ASIA_EN_BATCH_JOBS:
            assert batch in keys
            assert job_id == f"news_asia_en_{batch}_60m"
            assert label

    def test_no_url_overlap_with_existing_sources(self):
        """Every URL must be new — grep all shipped source modules."""
        src_dir = (
            Path(__file__).resolve().parents[2] / "services" / "news" / "sources"
        )
        url_re = re.compile(r"https?://[^\s\"'`)\]]+")
        taken: set[str] = set()
        for path in src_dir.glob("*.py"):
            if path.name == "asia_en_batch.py":
                continue
            taken.update(url_re.findall(path.read_text()))
        scheduler_jobs = (
            Path(__file__).resolve().parents[2] / "services" / "news" / "scheduler_jobs.py"
        )
        taken.update(url_re.findall(scheduler_jobs.read_text()))
        for _slug, _name, url, _market, _lang in ASIA_EN_FEEDS:
            assert url not in taken, url


class TestBatchCrawler:
    def _client(self, payload: str = _SAMPLE_RSS) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=payload)

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def test_fetch_recent_maps_per_feed_source_and_market(self):
        crawler = AsiaEnBatchCrawler("a", delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        batch = ASIA_EN_BATCHES["a"]
        expected_sources = {r[0] for r in batch}
        assert {a.source for a in articles} == expected_sources
        by_slug = {r[0]: r for r in batch}
        for a in articles:
            row = by_slug[a.source]
            assert a.market == row[3]
            assert a.language == row[4]
            assert "article body" in (a.body or "")

    def test_unknown_batch_is_empty_not_error(self):
        crawler = AsiaEnBatchCrawler("zzz", delay_seconds=0, client=self._client())
        assert asyncio.run(crawler.fetch_recent()) == []

    def test_failing_feed_does_not_break_batch(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = AsiaEnBatchCrawler("a", delay_seconds=0, client=client)
        assert asyncio.run(crawler.fetch_recent()) == []
