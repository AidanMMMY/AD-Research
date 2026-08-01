"""Tests for the official-institution & industry-vertical batch crawler (2026-08-01).

Covers:
  - The feed table has unique slugs/URLs and zero overlap against every
    earlier expansion wave (``indie_*`` / ``global_*`` / ``gind_*`` /
    ``asen_*`` / wechat2rss x3 / ``zhx_*`` podcasts / ``zhb_*`` blogs)
    **and** the ``rss_simple`` Fed/ECB/BoE-style singleton crawlers.
  - Batches partition the table completely into <=10-feed groups keyed
    ``a``-``f`` (the ``news_ofc_*`` job namespace is unique, so keys
    restart at ``a``).
  - ``OfficialBatchCrawler`` parses feeds into per-source articles with
    a mocked HTTP layer, honouring per-row market/language.
  - Scheduler wiring: ``scheduler_jobs.py`` materializes one ``run_*``
    function per batch and ``app/api/v1/news.py`` exposes health
    keywords/labels (wired 2026-08-02).
"""

from __future__ import annotations

import asyncio
import re

import httpx
import pytest

from app.services.news.sources.official_batch import (
    OFFICIAL_BATCH_JOBS,
    OFFICIAL_BATCHES,
    OFFICIAL_FEEDS,
    OfficialBatchCrawler,
)

_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{name}</title>
    <item>
      <title>Central bank holds rates steady, signals data dependence</title>
      <link>https://example.gov/press/1</link>
      <description>&lt;p&gt;The committee decided to maintain the policy rate.&lt;/p&gt;</description>
      <pubDate>Tue, 29 Jul 2026 18:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""

_BATCH_KEYS = list(OFFICIAL_BATCHES.keys())


class TestFeedTable:
    def test_unique_slugs_and_urls(self):
        slugs = [s for s, *_ in OFFICIAL_FEEDS]
        urls = [u for _, _, u, _, _ in OFFICIAL_FEEDS]
        assert len(slugs) == len(set(slugs))
        assert len(urls) == len(set(urls))

    def test_slug_format(self):
        for s, *_ in OFFICIAL_FEEDS:
            assert re.fullmatch(r"[a-z0-9]+", s), f"bad slug {s}"

    def test_market_and_language_values(self):
        # All rows are English official/industry sources. market must
        # stay "us": the DB-level "global" bucket is a frontend-only
        # sentinel (``_GLOBAL_MARKETS`` = cn_a/us/crypto), so storing
        # "global" would hide rows from the 全球 chip and break with
        # every earlier English wave's convention.
        for _, _, _, market, lang in OFFICIAL_FEEDS:
            assert market == "us"
            assert lang == "en"

    def test_at_least_50_sources(self):
        # Goal for this wave: 50-70 verified official/industry feeds.
        assert 50 <= len(OFFICIAL_FEEDS) <= 70

    def test_batches_partition_table(self):
        flat = [row for batch in OFFICIAL_BATCHES.values() for row in batch]
        assert flat == OFFICIAL_FEEDS

    def test_batch_keys_start_at_a(self):
        # news_ofc_* is its own job namespace, so keys restart at "a".
        assert min(_BATCH_KEYS) == "a"

    def test_batch_size_at_most_10(self):
        for key, batch in OFFICIAL_BATCHES.items():
            assert 0 < len(batch) <= 10, f"batch {key} has {len(batch)} feeds"

    def test_no_overlap_with_earlier_waves(self):
        from app.services.news.sources.asia_en_batch import ASIA_EN_FEEDS
        from app.services.news.sources.global_indie_batch import GLOBAL_INDIE_FEEDS
        from app.services.news.sources.global_rss_batch import GLOBAL_RSS_FEEDS
        from app.services.news.sources.independent_batch import INDEPENDENT_FEEDS
        from app.services.news.sources.wechat2rss_batch import WECHAT2RSS_FEEDS
        from app.services.news.sources.wechat2rss_batch2 import WECHAT2B_FEEDS
        from app.services.news.sources.wechat2rss_batch3 import WECHAT3_FEEDS
        from app.services.news.sources.zh_blog_batch import ZH_BLOG_FEEDS
        from app.services.news.sources.zh_multi_batch import ZH_MULTI_FEEDS

        other_urls = {u for _, _, u, _, _ in INDEPENDENT_FEEDS}
        other_urls |= {u for _, _, u, _, _ in GLOBAL_RSS_FEEDS}
        other_urls |= {u for _, _, u, _, _ in GLOBAL_INDIE_FEEDS}
        other_urls |= {u for _, _, u, _, _ in ASIA_EN_FEEDS}
        other_urls |= {u for _, _, u, _, _ in ZH_MULTI_FEEDS}
        other_urls |= {u for _, _, u, _, _ in ZH_BLOG_FEEDS}
        # wechat tables carry 3/4-tuples (slug, name, url[, ...]).
        other_urls |= {row[2] for row in WECHAT2RSS_FEEDS}
        other_urls |= {row[2] for row in WECHAT2B_FEEDS}
        other_urls |= {row[2] for row in WECHAT3_FEEDS}
        other_slugs = {s for s, *_ in INDEPENDENT_FEEDS}
        other_slugs |= {s for s, *_ in GLOBAL_RSS_FEEDS}
        other_slugs |= {s for s, *_ in GLOBAL_INDIE_FEEDS}
        other_slugs |= {s for s, *_ in ASIA_EN_FEEDS}
        other_slugs |= {s for s, *_ in ZH_MULTI_FEEDS}
        other_slugs |= {s for s, *_ in ZH_BLOG_FEEDS}
        other_slugs |= {row[0] for row in WECHAT2RSS_FEEDS}
        other_slugs |= {row[0] for row in WECHAT2B_FEEDS}
        other_slugs |= {row[0] for row in WECHAT3_FEEDS}
        for slug, _name, url, *_ in OFFICIAL_FEEDS:
            assert url not in other_urls, f"url already covered: {url}"
            assert slug not in other_slugs, f"slug already used: {slug}"

    def test_no_overlap_with_rss_simple(self):
        # rss_simple.py holds the singleton official crawlers (Fed
        # press_all, ECB press, BoE news, Calculated Risk ...) — this
        # wave must not re-add them under ofc_*.
        from app.services.news.sources import rss_simple

        simple_urls = {
            obj.feed_url
            for obj in vars(rss_simple).values()
            if isinstance(obj, type)
            and issubclass(obj, rss_simple.SimpleRssCrawler)
            and getattr(obj, "feed_url", "")
        }
        assert simple_urls, "rss_simple introspection yielded nothing"
        for slug, _name, url, *_ in OFFICIAL_FEEDS:
            assert url not in simple_urls, f"url already covered by rss_simple: {url}"

    def test_batch_jobs_match_batches(self):
        assert {b for _, _, b in OFFICIAL_BATCH_JOBS} == set(_BATCH_KEYS)
        for job_id, _label, batch in OFFICIAL_BATCH_JOBS:
            assert job_id == f"news_ofc_{batch}_60m"


class TestBatchCrawler:
    def _client(self) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_SAMPLE.format(name="Official Source"))

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def test_fetch_recent_maps_per_feed_source(self):
        crawler = OfficialBatchCrawler("a", delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        expected = {f"ofc_{s}" for s, *_ in OFFICIAL_BATCHES["a"]}
        assert {a.source for a in articles} == expected
        for a in articles:
            assert a.market == "us"
            assert a.language == "en"
            assert "policy rate" in (a.body or "")

    def test_every_batch_yields_articles(self):
        # Per-row market/language must survive for every batch, not
        # just the first (guards against tuple-order regressions).
        for key in _BATCH_KEYS:
            crawler = OfficialBatchCrawler(key, delay_seconds=0, client=self._client())
            articles = asyncio.run(crawler.fetch_recent())
            expected = {f"ofc_{s}" for s, *_ in OFFICIAL_BATCHES[key]}
            assert {a.source for a in articles} == expected
            assert all(a.market == "us" and a.language == "en" for a in articles)

    def test_unknown_batch_is_empty_not_error(self):
        crawler = OfficialBatchCrawler("zzz", delay_seconds=0, client=self._client())
        assert asyncio.run(crawler.fetch_recent()) == []

    def test_failing_feed_does_not_break_batch(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = OfficialBatchCrawler("a", delay_seconds=0, client=client)
        assert asyncio.run(crawler.fetch_recent()) == []


class TestSchedulerWiring:
    def test_batch_jobs_materialized(self):
        from app.services.news import scheduler_jobs as sj

        for job_id, _label, batch in sj.OFFICIAL_BATCH_JOBS:
            fn = getattr(sj, f"run_official_{batch}_crawl")
            assert callable(fn)
            assert fn.__name__ == f"run_official_{batch}_crawl"

    def test_job_table_covers_all_batches(self):
        from app.services.news import scheduler_jobs as sj

        assert {b for _, _, b in sj.OFFICIAL_BATCH_JOBS} == set(_BATCH_KEYS)

    @pytest.mark.parametrize("batch", _BATCH_KEYS)
    def test_health_meta_exists(self, batch):
        from app.api.v1.news import _WORKER_META

        assert f"news_ofc_{batch}_60m" in _WORKER_META

    def test_health_keyword_covers_job_ids(self):
        from app.api.v1.news import _WORKER_KEYWORDS

        assert any(k in "news_ofc_a_60m" for k in _WORKER_KEYWORDS)
