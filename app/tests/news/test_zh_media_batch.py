"""Tests for the Chinese-media / Asia / crypto increment batch crawler (2026-08-02).

Covers:
  - The feed table has unique slugs/URLs and zero overlap against every
    earlier expansion wave (``indie_*`` / ``global_*`` / ``gind_*`` /
    ``asen_*`` / wechat2rss x3 / ``zhx_*`` podcasts / ``zhb_*`` blogs).
  - Batches partition the table completely into <=10-feed groups keyed
    ``a``–``f`` (the ``news_zhm_*`` job namespace is unique, so keys
    restart at ``a``).
  - ``ZhMediaBatchCrawler`` parses feeds into per-source articles with a
    mocked HTTP layer, honouring per-row market/language.

Scheduler wiring (``scheduler_jobs.py`` / ``app/api/v1/news.py``) is
deliberately out of scope here — the coordinator session registers the
wave from :data:`ZH_MEDIA_BATCH_JOBS`, mirroring ``_zhb_batch_job``.
"""

from __future__ import annotations

import asyncio
import re

import httpx
import pytest

from app.services.news.sources.zh_media_batch import (
    ZH_MEDIA_BATCH_JOBS,
    ZH_MEDIA_BATCHES,
    ZH_MEDIA_FEEDS,
    ZhMediaBatchCrawler,
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

_BATCH_KEYS = list(ZH_MEDIA_BATCHES.keys())


class TestFeedTable:
    def test_unique_slugs_and_urls(self):
        slugs = [s for s, *_ in ZH_MEDIA_FEEDS]
        urls = [u for _, _, u, _, _ in ZH_MEDIA_FEEDS]
        assert len(slugs) == len(set(slugs))
        assert len(urls) == len(set(urls))

    def test_slug_format(self):
        for s, *_ in ZH_MEDIA_FEEDS:
            assert re.fullmatch(r"[a-z0-9_]+", s), f"bad slug {s}"

    def test_market_and_language_values(self):
        # market must stay inside the news API's _GLOBAL_MARKETS
        # whitelist (cn_a/us/crypto) — "global" would be invisible in
        # the frontend's default view (asia_en_batch precedent).
        for _, _, _, market, lang in ZH_MEDIA_FEEDS:
            assert market in {"cn_a", "us", "crypto"}
            assert lang in {"zh", "ja", "ko", "en"}

    def test_at_least_50_sources(self):
        # This wave is pure increment (the >=100 中文圈 goal was already
        # reached by wechat/zhx/zhb); the brief asked for 50-70.
        assert 50 <= len(ZH_MEDIA_FEEDS) <= 70

    def test_chinese_rows_use_cn_a_market(self):
        zh_rows = [r for r in ZH_MEDIA_FEEDS if r[4] == "zh"]
        assert zh_rows, "expected Chinese-language rows"
        for slug, _name, _url, market, _lang in zh_rows:
            assert market in {"cn_a", "crypto"}, f"{slug} zh row on {market}"

    def test_batches_partition_table(self):
        flat = [row for batch in ZH_MEDIA_BATCHES.values() for row in batch]
        assert flat == ZH_MEDIA_FEEDS

    def test_batch_keys_start_at_a(self):
        # news_zhm_* is its own job namespace, so keys restart at "a".
        assert min(_BATCH_KEYS) == "a"

    def test_batch_size_at_most_10(self):
        for key, batch in ZH_MEDIA_BATCHES.items():
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
        for slug, _name, url, *_ in ZH_MEDIA_FEEDS:
            assert url not in other_urls, f"url already covered: {url}"
            assert slug not in other_slugs, f"slug already used: {slug}"

    def test_batch_jobs_match_batches(self):
        assert {b for _, _, b in ZH_MEDIA_BATCH_JOBS} == set(_BATCH_KEYS)
        for job_id, _label, batch in ZH_MEDIA_BATCH_JOBS:
            assert job_id == f"news_zhm_{batch}_60m"


class TestBatchCrawler:
    def _client(self) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_SAMPLE.format(name="测试媒体"))

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def test_fetch_recent_maps_per_feed_source(self):
        crawler = ZhMediaBatchCrawler("a", delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        expected = {f"zhm_{s}" for s, *_ in ZH_MEDIA_BATCHES["a"]}
        assert {a.source for a in articles} == expected
        for a in articles:
            assert a.market == "cn_a"
            assert a.language == "zh"
            assert "独立分析" in (a.body or "")

    def test_crypto_rows_keep_own_market_and_language(self):
        # Batches e/f carry the crypto rows — the crawler must not
        # flatten per-row markets to cn_a or languages to zh.
        crawler = ZhMediaBatchCrawler("e", delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        by_source = {a.source: a for a in articles}
        crypto_rows = {f"zhm_{s}" for s, _, _, m, _ in ZH_MEDIA_BATCHES["e"] if m == "crypto"}
        assert crypto_rows
        for src in crypto_rows:
            assert by_source[src].market == "crypto"
        # Batch f mixes ja/ko crypto rows.
        crawler = ZhMediaBatchCrawler("f", delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        langs = {(a.source, a.language) for a in articles}
        expected = {
            (f"zhm_{s}", lang) for s, _, _, _, lang in ZH_MEDIA_BATCHES["f"]
        }
        assert langs == expected

    def test_unknown_batch_is_empty_not_error(self):
        crawler = ZhMediaBatchCrawler("zzz", delay_seconds=0, client=self._client())
        assert asyncio.run(crawler.fetch_recent()) == []

    def test_failing_feed_does_not_break_batch(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = ZhMediaBatchCrawler("a", delay_seconds=0, client=client)
        assert asyncio.run(crawler.fetch_recent()) == []


class TestJobGeometry:
    @pytest.mark.parametrize("batch", _BATCH_KEYS)
    def test_batch_key_roundtrips(self, batch):
        crawler = ZhMediaBatchCrawler(batch, delay_seconds=0)
        assert crawler.feeds, f"batch {batch} unexpectedly empty"
        for feed in crawler.feeds:
            assert feed.url.startswith("http")
            assert feed.display_name
