"""Tests for the English global-indie batch crawler (2026-07-28).

Covers:
  - The feed table obeys the independence selection rule (no official
    media / corporate-PR sources) and has unique slugs/URLs, with no
    overlap against the earlier expansion waves (``indie_*`` /
    ``global_*`` / wechat2rss).
  - Batches partition the table completely and start at key ``"o"``
    (``independent_batch`` owns ``a``–``n``).
  - ``GlobalIndieBatchCrawler`` parses feeds into per-source articles
    with a mocked HTTP layer, honouring per-row market/language.

Scheduler-wiring tests (``scheduler_jobs.GLOBAL_INDIE_BATCH_JOBS``
materialization and ``_WORKER_META`` health-grid entries) are skipped
until the integration patch lands — see
``docs/dev-notes/20260728-global-indie-batch-integration.md``.
"""

from __future__ import annotations

import asyncio
import re

import httpx
import pytest

from app.services.news.sources.global_indie_batch import (
    GLOBAL_INDIE_BATCH_JOBS,
    GLOBAL_INDIE_BATCHES,
    GLOBAL_INDIE_FEEDS,
    GlobalIndieBatchCrawler,
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
      <title>Weekly market wrap</title>
      <link>https://example.com/post-1</link>
      <description>&lt;p&gt;Full body paragraph.&lt;/p&gt;</description>
      <pubDate>Sun, 26 Jul 2026 22:47:18 +0000</pubDate>
    </item>
  </channel>
</rss>"""

_BATCH_KEYS = list(GLOBAL_INDIE_BATCHES.keys())


class TestFeedTable:
    def test_unique_slugs_and_urls(self):
        slugs = [s for s, *_ in GLOBAL_INDIE_FEEDS]
        urls = [u for _, _, u, _, _ in GLOBAL_INDIE_FEEDS]
        assert len(slugs) == len(set(slugs))
        assert len(urls) == len(set(urls))

    def test_slug_format(self):
        for s, *_ in GLOBAL_INDIE_FEEDS:
            assert re.fullmatch(r"[a-z0-9]+", s), f"bad slug {s}"

    def test_no_official_or_pr_sources(self):
        for _, name, *_ in GLOBAL_INDIE_FEEDS:
            for bad in _FORBIDDEN:
                assert bad not in name, f"{name} looks official/PR"

    def test_market_and_language_values(self):
        # English-only wave; market must stay inside the news API's
        # _GLOBAL_MARKETS whitelist (cn_a/us/crypto) or articles would
        # be hidden from the frontend's default filter.
        for _, _, _, market, lang in GLOBAL_INDIE_FEEDS:
            assert market in {"us", "crypto"}
            assert lang == "en"

    def test_all_https(self):
        # Every verified feed serves HTTPS; no exceptions this wave.
        for _, _, url, _, _ in GLOBAL_INDIE_FEEDS:
            assert url.startswith("https://"), f"unexpected non-https {url}"

    def test_batches_partition_table(self):
        flat = [row for batch in GLOBAL_INDIE_BATCHES.values() for row in batch]
        assert flat == GLOBAL_INDIE_FEEDS

    def test_batch_keys_start_at_o(self):
        # independent_batch owns a-n; this wave must not collide.
        assert min(_BATCH_KEYS) == "o"

    def test_at_least_100_sources(self):
        assert len(GLOBAL_INDIE_FEEDS) >= 100

    def test_no_overlap_with_earlier_waves(self):
        from app.services.news.sources.global_rss_batch import GLOBAL_RSS_FEEDS
        from app.services.news.sources.independent_batch import INDEPENDENT_FEEDS

        other_urls = {u for _, _, u, _, _ in INDEPENDENT_FEEDS}
        other_urls |= {u for _, _, u, _, _ in GLOBAL_RSS_FEEDS}
        other_slugs = {s for s, *_ in INDEPENDENT_FEEDS}
        other_slugs |= {s for s, *_ in GLOBAL_RSS_FEEDS}
        for slug, _name, url, *_ in GLOBAL_INDIE_FEEDS:
            assert url not in other_urls, f"url already covered: {url}"
            assert slug not in other_slugs, f"slug already used: {slug}"

    def test_batch_jobs_match_batches(self):
        assert {b for _, _, b in GLOBAL_INDIE_BATCH_JOBS} == set(_BATCH_KEYS)
        for job_id, _label, batch in GLOBAL_INDIE_BATCH_JOBS:
            assert job_id == f"news_gind_{batch}_60m"


class TestBatchCrawler:
    def _client(self) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_SAMPLE.format(name="Test Source"))

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def test_fetch_recent_maps_per_feed_source(self):
        crawler = GlobalIndieBatchCrawler("o", delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        expected = {f"gind_{s}" for s, *_ in GLOBAL_INDIE_BATCHES["o"]}
        assert {a.source for a in articles} == expected
        market_by_slug = {s: m for s, _, _, m, _ in GLOBAL_INDIE_BATCHES["o"]}
        lang_by_slug = {s: lang for s, _, _, _, lang in GLOBAL_INDIE_BATCHES["o"]}
        for a in articles:
            slug = a.source.removeprefix("gind_")
            assert a.market == market_by_slug[slug]
            assert a.language == lang_by_slug[slug]
            assert "Full body paragraph" in (a.body or "")

    def test_unknown_batch_is_empty_not_error(self):
        crawler = GlobalIndieBatchCrawler("zzz", delay_seconds=0, client=self._client())
        assert asyncio.run(crawler.fetch_recent()) == []

    def test_failing_feed_does_not_break_batch(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = GlobalIndieBatchCrawler("o", delay_seconds=0, client=client)
        assert asyncio.run(crawler.fetch_recent()) == []


class TestSchedulerWiring:
    """Pending the main-session integration patch — see
    ``docs/dev-notes/20260728-global-indie-batch-integration.md``.
    The skipped assertions below become active once scheduler_jobs.py,
    core/scheduler.py and api/v1/news.py are updated.
    """

    def test_batch_jobs_materialized(self):
        from app.services.news import scheduler_jobs as sj

        for job_id, _label, batch in sj.GLOBAL_INDIE_BATCH_JOBS:
            fn = getattr(sj, f"run_global_indie_{batch}_crawl")
            assert callable(fn)
            assert fn.__name__ == f"run_global_indie_{batch}_crawl"

    def test_job_table_covers_all_batches(self):
        from app.services.news import scheduler_jobs as sj

        assert {b for _, _, b in sj.GLOBAL_INDIE_BATCH_JOBS} == set(_BATCH_KEYS)

    @pytest.mark.parametrize("batch", _BATCH_KEYS)
    def test_health_meta_exists(self, batch):
        from app.api.v1.news import _WORKER_META

        assert f"news_gind_{batch}_60m" in _WORKER_META

    def test_health_keyword_covers_job_ids(self):
        from app.api.v1.news import _WORKER_KEYWORDS

        assert any(k in "news_gind_o_60m" for k in _WORKER_KEYWORDS)
