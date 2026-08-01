"""Tests for the investment-education batch crawler (2026-08-02).

Covers:
  - The feed table has unique slugs/URLs, https-only URLs, and zero
    overlap against every earlier expansion wave (``indie_*`` /
    ``global_*`` / ``gind_*`` / ``asen_*`` / ``zhx_*`` / ``zhb_*`` /
    ``enf_*`` / ``ofc_*`` / ``zhm_*`` / wechat2rss waves) and the
    single-feed ``rss_simple`` crawlers.
  - Batches partition the table completely into <=10-feed groups keyed
    ``a``–``b`` (the ``news_edu_*`` job namespace is unique, so keys
    restart at ``a``).
  - Per-row market/language stay inside the news API's
    ``_GLOBAL_MARKETS`` whitelist (English rows are market="us" —
    market="global" would be invisible in the default frontend filter).
  - ``EduBatchCrawler`` parses feeds into per-source articles with a
    mocked HTTP layer, honouring per-row market/language, and promotes
    YouTube ``media:description`` into the article body.

No scheduler-wiring tests here on purpose: the wave is wired into
``scheduler_jobs.py`` / ``app/core/scheduler.py`` /
``app/api/v1/news.py`` by the coordinating session in a separate commit
(same precedent as the en_fin wave).
"""

from __future__ import annotations

import asyncio
import re

import httpx

from app.services.news.sources.edu_batch import (
    EDU_BATCH_JOBS,
    EDU_BATCHES,
    EDU_FEEDS,
    EduBatchCrawler,
    _youtube_descriptions_to_summary,
)

_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{name}</title>
    <item>
      <title>What is an index fund? A beginner's guide</title>
      <link>https://example.com/article-1</link>
      <description>&lt;p&gt;An evergreen explainer on low-cost diversified investing.&lt;/p&gt;</description>
      <pubDate>Sat, 01 Aug 2026 14:30:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""

# YouTube-style Atom: bodies live in media:group/media:description.
_YT_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
  <title>{name}</title>
  <entry>
    <id>yt:video:abcdefghijk</id>
    <title>What is an index fund?</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=abcdefghijk"/>
    <author><name>{name}</name></author>
    <published>2026-07-30T15:00:00+00:00</published>
    <media:group>
      <media:title>What is an index fund?</media:title>
      <media:description>VIDEO-DESC-MARKER: an evergreen explainer on low-cost diversified investing.</media:description>
    </media:group>
  </entry>
</feed>"""

_BATCH_KEYS = list(EDU_BATCHES.keys())


class TestFeedTable:
    def test_unique_slugs_and_urls(self):
        slugs = [s for s, *_ in EDU_FEEDS]
        urls = [u for _, _, u, _, _ in EDU_FEEDS]
        assert len(slugs) == len(set(slugs))
        assert len(urls) == len(set(urls))

    def test_slug_format(self):
        for s, *_ in EDU_FEEDS:
            assert re.fullmatch(r"[a-z0-9]+", s), f"bad slug {s}"

    def test_urls_are_https(self):
        for _, _, url, _, _ in EDU_FEEDS:
            assert url.startswith("https://"), f"non-https url: {url}"

    def test_market_and_language_values(self):
        # market must stay inside the news API's _GLOBAL_MARKETS
        # whitelist (cn_a/us/crypto) — market="global" rows would be
        # invisible in the frontend's default filter (see module
        # docstring; same ruling as asia_en_batch / en_fin_batch).
        for _, _, _, market, lang in EDU_FEEDS:
            assert market in {"cn_a", "us"}
            assert lang in {"en", "zh"}

    def test_source_count_in_brief_range(self):
        # Wave goal: 15-25 curated education feeds (贵精不贵多).
        assert 15 <= len(EDU_FEEDS) <= 25

    def test_batches_partition_table(self):
        flat = [row for batch in EDU_BATCHES.values() for row in batch]
        assert flat == EDU_FEEDS

    def test_batch_keys_start_at_a(self):
        # news_edu_* is its own job namespace, so keys restart at "a".
        assert min(_BATCH_KEYS) == "a"

    def test_batch_size_at_most_10(self):
        for key, batch in EDU_BATCHES.items():
            assert 0 < len(batch) <= 10, f"batch {key} has {len(batch)} feeds"

    def test_no_overlap_with_earlier_waves(self):
        from app.services.news.sources.asia_en_batch import ASIA_EN_FEEDS
        from app.services.news.sources.en_fin_batch import EN_FIN_FEEDS
        from app.services.news.sources.global_indie_batch import GLOBAL_INDIE_FEEDS
        from app.services.news.sources.global_rss_batch import GLOBAL_RSS_FEEDS
        from app.services.news.sources.independent_batch import INDEPENDENT_FEEDS
        from app.services.news.sources.official_batch import OFFICIAL_FEEDS
        from app.services.news.sources.wechat2rss_batch import WECHAT2RSS_FEEDS
        from app.services.news.sources.wechat2rss_batch2 import WECHAT2B_FEEDS
        from app.services.news.sources.wechat2rss_batch3 import WECHAT3_FEEDS
        from app.services.news.sources.zh_blog_batch import ZH_BLOG_FEEDS
        from app.services.news.sources.zh_media_batch import ZH_MEDIA_FEEDS
        from app.services.news.sources.zh_multi_batch import ZH_MULTI_FEEDS

        other_urls = {u for _, _, u, _, _ in INDEPENDENT_FEEDS}
        other_urls |= {u for _, _, u, _, _ in GLOBAL_RSS_FEEDS}
        other_urls |= {u for _, _, u, _, _ in GLOBAL_INDIE_FEEDS}
        other_urls |= {u for _, _, u, _, _ in ASIA_EN_FEEDS}
        other_urls |= {u for _, _, u, _, _ in ZH_MULTI_FEEDS}
        other_urls |= {u for _, _, u, _, _ in ZH_BLOG_FEEDS}
        other_urls |= {u for _, _, u, _, _ in EN_FIN_FEEDS}
        other_urls |= {u for _, _, u, _, _ in OFFICIAL_FEEDS}
        other_urls |= {u for _, _, u, _, _ in ZH_MEDIA_FEEDS}
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
        other_slugs |= {s for s, *_ in EN_FIN_FEEDS}
        other_slugs |= {s for s, *_ in OFFICIAL_FEEDS}
        other_slugs |= {s for s, *_ in ZH_MEDIA_FEEDS}
        other_slugs |= {row[0] for row in WECHAT2RSS_FEEDS}
        other_slugs |= {row[0] for row in WECHAT2B_FEEDS}
        other_slugs |= {row[0] for row in WECHAT3_FEEDS}
        for slug, _name, url, *_ in EDU_FEEDS:
            assert url not in other_urls, f"url already covered: {url}"
            assert slug not in other_slugs, f"slug already used: {slug}"

    def test_no_overlap_with_single_feed_crawlers(self):
        # A Wealth of Common Sense / Of Dollars and Data etc. live in
        # rss_simple.py as parameterized crawlers, not batch tables —
        # guard against re-adding their URLs here.
        forbidden = {
            "https://awealthofcommonsense.com/feed/",
            "https://ofdollarsanddata.com/feed/",
            "https://ritholtz.com/feed/",
        }
        for _, _, url, *_ in EDU_FEEDS:
            assert url not in forbidden, f"single-crawler url re-added: {url}"

    def test_batch_jobs_match_batches(self):
        assert {b for _, _, b in EDU_BATCH_JOBS} == set(_BATCH_KEYS)
        for job_id, _label, batch in EDU_BATCH_JOBS:
            assert job_id == f"news_edu_{batch}_60m"


class TestBatchCrawler:
    def _client(self, sample: str = _SAMPLE) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=sample.format(name="Test Edu Feed"))

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def test_fetch_recent_maps_per_feed_source(self):
        crawler = EduBatchCrawler("a", delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        expected = {f"edu_{s}" for s, *_ in EDU_BATCHES["a"]}
        assert {a.source for a in articles} == expected
        for a in articles:
            assert a.market == "us"
            assert a.language == "en"
            assert "evergreen explainer" in (a.body or "")

    def test_last_batch_keeps_per_row_market_and_language(self):
        # Batch "b" mixes YouTube rows (us/en) with stockfeel (cn_a/zh)
        # — the crawler must not flatten per-row market/language.
        crawler = EduBatchCrawler("b", delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        by_source = {a.source: a for a in articles}
        for slug, _n, _u, market, lang in EDU_BATCHES["b"]:
            art = by_source[f"edu_{slug}"]
            assert art.market == market
            assert art.language == lang

    def test_last_batch_is_partial_not_empty(self):
        # 17 feeds = one full batch "a" of 10 + one partial batch "b" of 7.
        last_key = max(EDU_BATCHES)
        crawler = EduBatchCrawler(last_key, delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        expected = {f"edu_{s}" for s, *_ in EDU_BATCHES[last_key]}
        assert {a.source for a in articles} == expected
        assert len(EDU_BATCHES[last_key]) == len(EDU_FEEDS) % 10

    def test_youtube_rows_get_video_description_body(self):
        # Batch "b" holds 6 YouTube rows: with an Atom sample whose body
        # lives in media:description, yt sources must ingest the
        # description as the article body (non-yt rows read the native
        # Atom summary path — the sample carries no summary, so their
        # bodies are simply empty; only the marker assertion matters).
        crawler = EduBatchCrawler("b", delay_seconds=0, client=self._client(_YT_SAMPLE))
        articles = asyncio.run(crawler.fetch_recent())
        yt_sources = {f"edu_{s}" for s, *_ in EDU_BATCHES["b"] if s.startswith("yt")}
        assert yt_sources, "batch b must contain YouTube rows for this test"
        by_source = {a.source: a for a in articles}
        for src in yt_sources:
            assert "VIDEO-DESC-MARKER" in (by_source[src].body or "")
            assert by_source[src].url.startswith("https://www.youtube.com/watch")

    def test_unknown_batch_is_empty_not_error(self):
        crawler = EduBatchCrawler("zzz", delay_seconds=0, client=self._client())
        assert asyncio.run(crawler.fetch_recent()) == []

    def test_failing_feed_does_not_break_batch(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = EduBatchCrawler("a", delay_seconds=0, client=client)
        assert asyncio.run(crawler.fetch_recent()) == []

    def test_max_items_per_feed_honoured(self):
        many_items = (
            '<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>'
            + "".join(
                f"<item><title>t{i}</title><link>https://example.com/{i}</link>"
                f"<description>lesson {i} with enough text</description>"
                f"<pubDate>Sat, 01 Aug 2026 10:00:0{i % 10} +0000</pubDate></item>"
                for i in range(25)
            )
            + "</channel></rss>"
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=many_items)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = EduBatchCrawler("a", delay_seconds=0, max_items_per_feed=5, client=client)
        articles = asyncio.run(crawler.fetch_recent())
        per_source: dict[str, int] = {}
        for a in articles:
            per_source[a.source] = per_source.get(a.source, 0) + 1
        assert per_source
        assert all(n <= 5 for n in per_source.values())


class TestYouTubeDescriptionInjection:
    """Unit tests for the media:description → atom:summary promotion."""

    def test_injects_description_into_summary(self):
        out = _youtube_descriptions_to_summary(_YT_SAMPLE.format(name="Ch"))
        assert "VIDEO-DESC-MARKER" in out
        from app.services.news.sources.rss_common import parse_rss_items

        articles = parse_rss_items(out, source="edu_test", market="us", language="en")
        assert len(articles) == 1
        assert "VIDEO-DESC-MARKER" in (articles[0].body or "")
        assert articles[0].url == "https://www.youtube.com/watch?v=abcdefghijk"
        assert articles[0].published_at.year == 2026

    def test_existing_summary_is_not_overwritten(self):
        xml = (
            '<?xml version="1.0"?>'
            '<feed xmlns:media="http://search.yahoo.com/mrss/" '
            'xmlns="http://www.w3.org/2005/Atom">'
            "<entry><id>yt:video:x</id><title>t</title>"
            '<link rel="alternate" href="https://www.youtube.com/watch?v=x"/>'
            "<summary>ORIGINAL-SUMMARY</summary>"
            "<media:group><media:description>SHOULD-NOT-WIN</media:description>"
            "</media:group></entry></feed>"
        )
        out = _youtube_descriptions_to_summary(xml)
        from app.services.news.sources.rss_common import parse_rss_items

        articles = parse_rss_items(out, source="edu_test")
        # The pre-existing <summary> wins; the media description is left
        # in place but never promoted.
        assert articles[0].body == "ORIGINAL-SUMMARY"

    def test_malformed_xml_returned_unchanged(self):
        garbage = "<feed><entry><unclosed"
        assert _youtube_descriptions_to_summary(garbage) == garbage
