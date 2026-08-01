"""Tests for the English finance batch crawler (2026-08-02).

Covers:
  - The feed table has unique slugs/URLs, https-only URLs, and zero
    overlap against every earlier expansion wave (``indie_*`` /
    ``global_*`` / ``gind_*`` / ``asen_*`` / wechat2rss waves /
    ``zhx_*`` podcasts / ``zhb_*`` blogs).
  - Batches partition the table completely into <=10-feed groups keyed
    ``a``–``g`` (the ``news_enf_*`` job namespace is unique, so keys
    restart at ``a``).
  - Per-row market/language stay inside the news API's
    ``_GLOBAL_MARKETS`` whitelist (market="us" everywhere — market=
    "global" would be invisible in the default frontend filter, see
    the module docstring).
  - ``EnFinBatchCrawler`` parses feeds into per-source articles with a
    mocked HTTP layer, honouring per-row market/language.

No scheduler-wiring tests here on purpose: the wave is wired into
``scheduler_jobs.py`` / ``app/api/v1/news.py`` by the coordinating
session in a separate commit.
"""

from __future__ import annotations

import asyncio
import re

import httpx

from app.services.news.sources.en_fin_batch import (
    EN_FIN_BATCH_JOBS,
    EN_FIN_BATCHES,
    EN_FIN_FEEDS,
    EnFinBatchCrawler,
)

_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{name}</title>
    <item>
      <title>Fed officials signal patience on rate path</title>
      <link>https://example.com/article-1</link>
      <description>&lt;p&gt;Officials said they need more evidence that inflation is moving sustainably toward target before cutting rates.&lt;/p&gt;</description>
      <pubDate>Sat, 01 Aug 2026 14:30:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""

_BATCH_KEYS = list(EN_FIN_BATCHES.keys())


class TestFeedTable:
    def test_unique_slugs_and_urls(self):
        slugs = [s for s, *_ in EN_FIN_FEEDS]
        urls = [u for _, _, u, _, _ in EN_FIN_FEEDS]
        assert len(slugs) == len(set(slugs))
        assert len(urls) == len(set(urls))

    def test_slug_format(self):
        for s, *_ in EN_FIN_FEEDS:
            assert re.fullmatch(r"[a-z0-9]+", s), f"bad slug {s}"

    def test_urls_are_https(self):
        for _, _, url, _, _ in EN_FIN_FEEDS:
            assert url.startswith("https://"), f"non-https url: {url}"

    def test_market_and_language_values(self):
        # market must stay inside the news API's _GLOBAL_MARKETS
        # whitelist (cn_a/us/crypto) — market="global" rows would be
        # invisible in the frontend's default filter (see module
        # docstring; same ruling as asia_en_batch).
        for _, _, _, market, lang in EN_FIN_FEEDS:
            assert market in {"cn_a", "us", "crypto"}
            assert lang == "en"

    def test_at_least_50_sources(self):
        # Wave goal: 50-70 verified English finance feeds.
        assert 50 <= len(EN_FIN_FEEDS) <= 70

    def test_batches_partition_table(self):
        flat = [row for batch in EN_FIN_BATCHES.values() for row in batch]
        assert flat == EN_FIN_FEEDS

    def test_batch_keys_start_at_a(self):
        # news_enf_* is its own job namespace, so keys restart at "a".
        assert min(_BATCH_KEYS) == "a"

    def test_batch_size_at_most_10(self):
        for key, batch in EN_FIN_BATCHES.items():
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
        for slug, _name, url, *_ in EN_FIN_FEEDS:
            assert url not in other_urls, f"url already covered: {url}"
            assert slug not in other_slugs, f"slug already used: {slug}"

    def test_no_overlap_with_single_feed_crawlers(self):
        # CNBC combinedcms / MarketWatch topstories / Yahoo / Seeking
        # Alpha / FT / Guardian etc. live in single-feed modules, not
        # batch tables — guard against re-adding their domains+paths.
        forbidden = {
            "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
            "https://feeds.marketwatch.com/marketwatch/topstories/",
            "https://feeds.finance.yahoo.com/rss/2.0/headline",
            "https://seekingalpha.com/market_currents.xml",
        }
        for _, _, url, *_ in EN_FIN_FEEDS:
            assert url not in forbidden, f"single-crawler url re-added: {url}"

    def test_batch_jobs_match_batches(self):
        assert {b for _, _, b in EN_FIN_BATCH_JOBS} == set(_BATCH_KEYS)
        for job_id, _label, batch in EN_FIN_BATCH_JOBS:
            assert job_id == f"news_enf_{batch}_60m"


class TestBatchCrawler:
    def _client(self) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_SAMPLE.format(name="Test Finance Feed"))

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def test_fetch_recent_maps_per_feed_source(self):
        crawler = EnFinBatchCrawler("a", delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        expected = {f"enf_{s}" for s, *_ in EN_FIN_BATCHES["a"]}
        assert {a.source for a in articles} == expected
        for a in articles:
            assert a.market == "us"
            assert a.language == "en"
            assert "inflation" in (a.body or "")

    def test_last_batch_is_partial_not_empty(self):
        # 56 feeds = 5 full batches + one partial batch "f" of 6.
        last_key = max(EN_FIN_BATCHES)
        crawler = EnFinBatchCrawler(last_key, delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        expected = {f"enf_{s}" for s, *_ in EN_FIN_BATCHES[last_key]}
        assert {a.source for a in articles} == expected
        assert len(EN_FIN_BATCHES[last_key]) == len(EN_FIN_FEEDS) % 10

    def test_unknown_batch_is_empty_not_error(self):
        crawler = EnFinBatchCrawler("zzz", delay_seconds=0, client=self._client())
        assert asyncio.run(crawler.fetch_recent()) == []

    def test_failing_feed_does_not_break_batch(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = EnFinBatchCrawler("a", delay_seconds=0, client=client)
        assert asyncio.run(crawler.fetch_recent()) == []

    def test_max_items_per_feed_honoured(self):
        many_items = (
            '<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>'
            + "".join(
                f"<item><title>t{i}</title><link>https://example.com/{i}</link>"
                f"<description>body {i} with enough text</description>"
                f"<pubDate>Sat, 01 Aug 2026 10:00:0{i % 10} +0000</pubDate></item>"
                for i in range(25)
            )
            + "</channel></rss>"
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=many_items)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = EnFinBatchCrawler("a", delay_seconds=0, max_items_per_feed=5, client=client)
        articles = asyncio.run(crawler.fetch_recent())
        per_source: dict[str, int] = {}
        for a in articles:
            per_source[a.source] = per_source.get(a.source, 0) + 1
        assert per_source
        assert all(n <= 5 for n in per_source.values())
