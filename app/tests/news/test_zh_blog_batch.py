"""Tests for the Chinese blog batch crawler (2026-07-30).

Covers:
  - The feed table has unique slugs/URLs and zero overlap against every
    earlier expansion wave (``indie_*`` / ``global_*`` / ``gind_*`` /
    ``asen_*`` / wechat2rss / ``zhx_*`` podcasts).
  - Batches partition the table completely into <=10-feed groups keyed
    ``a``–``d`` (the ``news_zhb_*`` job namespace is unique, so keys
    restart at ``a``).
  - ``ZhBlogBatchCrawler`` parses feeds into per-source articles with a
    mocked HTTP layer, honouring per-row market/language.
"""

from __future__ import annotations

import asyncio
import re

import httpx
import pytest

from app.services.news.sources.zh_blog_batch import (
    ZH_BLOG_BATCH_JOBS,
    ZH_BLOG_BATCHES,
    ZH_BLOG_FEEDS,
    ZhBlogBatchCrawler,
)

# Names that must never appear in the table — official domestic media or
# corporate-brand PR channels (user requirement: independent voices).
_FORBIDDEN = (
    "人民日报", "新华社", "央视", "官方", "集团", "研究所",
)

_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{name}</title>
    <item>
      <title>一篇有独立观点的深度评论</title>
      <link>https://example.com/post-1</link>
      <description>&lt;p&gt;这是正文段落，包含作者的独立分析与判断。&lt;/p&gt;</description>
      <pubDate>Tue, 29 Jul 2026 22:47:18 +0000</pubDate>
    </item>
  </channel>
</rss>"""

_BATCH_KEYS = list(ZH_BLOG_BATCHES.keys())


class TestFeedTable:
    def test_unique_slugs_and_urls(self):
        slugs = [s for s, *_ in ZH_BLOG_FEEDS]
        urls = [u for _, _, u, _, _ in ZH_BLOG_FEEDS]
        assert len(slugs) == len(set(slugs))
        assert len(urls) == len(set(urls))

    def test_slug_format(self):
        for s, *_ in ZH_BLOG_FEEDS:
            assert re.fullmatch(r"[a-z0-9]+", s), f"bad slug {s}"

    def test_no_official_or_pr_sources(self):
        for _, name, *_ in ZH_BLOG_FEEDS:
            for bad in _FORBIDDEN:
                assert bad not in name, f"{name} looks official/PR"

    def test_market_and_language_values(self):
        # Chinese-language wave; market must stay inside the news API's
        # _GLOBAL_MARKETS whitelist (cn_a/us/crypto) or articles would
        # be hidden from the frontend's default filter.
        for _, _, _, market, lang in ZH_BLOG_FEEDS:
            assert market in {"cn_a", "crypto"}
            assert lang in {"zh", "en"}

    def test_at_least_35_sources(self):
        # 62 (wechat3 + podcasts) + >=38 here reaches the >=100 goal.
        assert len(ZH_BLOG_FEEDS) >= 35

    def test_batches_partition_table(self):
        flat = [row for batch in ZH_BLOG_BATCHES.values() for row in batch]
        assert flat == ZH_BLOG_FEEDS

    def test_batch_keys_start_at_a(self):
        # news_zhb_* is its own job namespace, so keys restart at "a".
        assert min(_BATCH_KEYS) == "a"

    def test_batch_size_at_most_10(self):
        for key, batch in ZH_BLOG_BATCHES.items():
            assert 0 < len(batch) <= 10, f"batch {key} has {len(batch)} feeds"

    def test_no_overlap_with_earlier_waves(self):
        from app.services.news.sources.asia_en_batch import ASIA_EN_FEEDS
        from app.services.news.sources.global_indie_batch import GLOBAL_INDIE_FEEDS
        from app.services.news.sources.global_rss_batch import GLOBAL_RSS_FEEDS
        from app.services.news.sources.independent_batch import INDEPENDENT_FEEDS
        from app.services.news.sources.wechat2rss_batch import WECHAT2RSS_FEEDS
        from app.services.news.sources.wechat2rss_batch2 import WECHAT2B_FEEDS
        from app.services.news.sources.zh_multi_batch import ZH_MULTI_FEEDS

        other_urls = {u for _, _, u, _, _ in INDEPENDENT_FEEDS}
        other_urls |= {u for _, _, u, _, _ in GLOBAL_RSS_FEEDS}
        other_urls |= {u for _, _, u, _, _ in GLOBAL_INDIE_FEEDS}
        other_urls |= {u for _, _, u, _, _ in ASIA_EN_FEEDS}
        other_urls |= {u for _, _, u, _, _ in ZH_MULTI_FEEDS}
        # wechat tables carry 3/4-tuples (slug, name, url[, ...]).
        other_urls |= {row[2] for row in WECHAT2RSS_FEEDS}
        other_urls |= {row[2] for row in WECHAT2B_FEEDS}
        other_slugs = {s for s, *_ in INDEPENDENT_FEEDS}
        other_slugs |= {s for s, *_ in GLOBAL_RSS_FEEDS}
        other_slugs |= {s for s, *_ in GLOBAL_INDIE_FEEDS}
        other_slugs |= {s for s, *_ in ASIA_EN_FEEDS}
        other_slugs |= {s for s, *_ in ZH_MULTI_FEEDS}
        other_slugs |= {row[0] for row in WECHAT2RSS_FEEDS}
        other_slugs |= {row[0] for row in WECHAT2B_FEEDS}
        for slug, _name, url, *_ in ZH_BLOG_FEEDS:
            assert url not in other_urls, f"url already covered: {url}"
            assert slug not in other_slugs, f"slug already used: {slug}"

    def test_batch_jobs_match_batches(self):
        assert {b for _, _, b in ZH_BLOG_BATCH_JOBS} == set(_BATCH_KEYS)
        for job_id, _label, batch in ZH_BLOG_BATCH_JOBS:
            assert job_id == f"news_zhb_{batch}_60m"


class TestBatchCrawler:
    def _client(self) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_SAMPLE.format(name="测试博客"))

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def test_fetch_recent_maps_per_feed_source(self):
        crawler = ZhBlogBatchCrawler("a", delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        expected = {f"zhb_{s}" for s, *_ in ZH_BLOG_BATCHES["a"]}
        assert {a.source for a in articles} == expected
        for a in articles:
            assert a.market == "cn_a"
            assert a.language == "zh"
            assert "独立分析" in (a.body or "")

    def test_crypto_batch_rows_keep_own_market(self):
        # 動區動趨 / 桑幣區識 carry market=crypto — the crawler must not
        # flatten per-row markets to cn_a.
        crawler = ZhBlogBatchCrawler("c", delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        by_source = {a.source: a for a in articles}
        crypto_rows = {f"zhb_{s}" for s, _, _, m, _ in ZH_BLOG_BATCHES["c"] if m == "crypto"}
        for src in crypto_rows:
            assert by_source[src].market == "crypto"

    def test_unknown_batch_is_empty_not_error(self):
        crawler = ZhBlogBatchCrawler("zzz", delay_seconds=0, client=self._client())
        assert asyncio.run(crawler.fetch_recent()) == []

    def test_failing_feed_does_not_break_batch(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = ZhBlogBatchCrawler("a", delay_seconds=0, client=client)
        assert asyncio.run(crawler.fetch_recent()) == []


class TestSchedulerWiring:
    def test_batch_jobs_materialized(self):
        from app.services.news import scheduler_jobs as sj

        for job_id, _label, batch in sj.ZH_BLOG_BATCH_JOBS:
            fn = getattr(sj, f"run_zh_blog_{batch}_crawl")
            assert callable(fn)
            assert fn.__name__ == f"run_zh_blog_{batch}_crawl"

    def test_job_table_covers_all_batches(self):
        from app.services.news import scheduler_jobs as sj

        assert {b for _, _, b in sj.ZH_BLOG_BATCH_JOBS} == set(_BATCH_KEYS)

    @pytest.mark.parametrize("batch", _BATCH_KEYS)
    def test_health_meta_exists(self, batch):
        from app.api.v1.news import _WORKER_META

        assert f"news_zhb_{batch}_60m" in _WORKER_META

    def test_health_keyword_covers_job_ids(self):
        from app.api.v1.news import _WORKER_KEYWORDS

        assert any(k in "news_zhb_a_60m" for k in _WORKER_KEYWORDS)
