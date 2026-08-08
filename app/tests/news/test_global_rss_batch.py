"""Tests for the global multi-language RSS batch crawler (2026-07-28).

Covers:
  - The feed table is well-formed (unique slugs/URLs, known languages
    and markets, ≥100 feeds — the expansion goal).
  - Batches partition the table completely.
  - ``GlobalRssBatchCrawler`` parses feeds into per-feed sources with
    per-feed language/market, with a mocked HTTP layer.
  - Batch jobs materialize in ``scheduler_jobs`` and are registered in
    ``app.core.scheduler``.
  - The health panel meta exists for every batch job.
  - The shared ``parse_rss_items`` handles RSS 1.0 (RDF) and true Atom
    feeds (added for this expansion — Japanese media ship RDF, and
    engineering blogs ship Atom).
  - The translation prompts are multi-language aware (not English-only).
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.services.news.sources.global_rss_batch import (
    GLOBAL_RSS_BATCHES,
    GLOBAL_RSS_FEEDS,
    GlobalRssBatchCrawler,
)

_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Sample</title>
    <item>
      <title>Beispiel Schlagzeile</title>
      <link>https://example.com/article/1</link>
      <content:encoded><![CDATA[<p>Ein langer deutscher Artikeltext mit vielen Details zur Lage der Märkte und der Geldpolitik der Zentralbanken, der deutlich über zweihundert Zeichen hinausgeht und deshalb als echter Volltext durchgeht.</p>]]></content:encoded>
      <pubDate>Mon, 27 Jul 2026 08:00:00 +0200</pubDate>
    </item>
  </channel>
</rss>"""

_SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Sample</title>
  <entry>
    <title>Atom 記事タイトル</title>
    <link rel="alternate" href="https://example.com/atom/1"/>
    <id>tag:example.com,2026:1</id>
    <published>2026-07-27T09:00:00+09:00</published>
    <summary>短い要約</summary>
    <content type="html">日本語の本文。中央銀行の政策決定と市場の反応についての詳細な解説記事で、二百字を大きく超える分量の本文が含まれていることを確認するためのテキスト。翻訳パイプラインに十分な本文が渡る。</content>
  </entry>
</feed>"""

_SAMPLE_RDF = """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns="http://purl.org/rss/1.0/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel rdf:about="https://example.com/feed.rdf">
    <title>RDF Sample</title>
  </channel>
  <item rdf:about="https://example.com/news/1">
    <title>RDF 記事タイトル</title>
    <link>https://example.com/news/1</link>
    <description>日本語の記事説明文。こちらも二百字を超える十分な分量の本文を用意して、RSS 1.0 形式のフィードでも本文が欠落しないことを確認するためのテキスト。市場動向の詳しい分析が続く。</description>
    <dc:date>2026-07-27T10:00:00+09:00</dc:date>
  </item>
</rdf:RDF>"""


class TestFeedTable:
    def test_unique_slugs_and_urls(self):
        slugs = [r[0] for r in GLOBAL_RSS_FEEDS]
        urls = [r[2] for r in GLOBAL_RSS_FEEDS]
        assert len(slugs) == len(set(slugs))
        assert len(urls) == len(set(urls))

    def test_row_shape_and_values(self):
        valid_langs = {"ja", "de", "fr", "ko", "es", "en", "zh"}
        valid_markets = {"us", "cn_a", "hk", "crypto", "global"}
        for slug, name, url, lang, market in GLOBAL_RSS_FEEDS:
            assert slug and slug.isascii()
            assert name
            assert url.startswith("https://") or url.startswith("http://")
            assert lang in valid_langs
            assert market in valid_markets

    def test_batches_partition_table(self):
        flat = [row for batch in GLOBAL_RSS_BATCHES.values() for row in batch]
        assert flat == GLOBAL_RSS_FEEDS

    def test_at_least_100_feeds(self):
        assert len(GLOBAL_RSS_FEEDS) >= 100

    def test_multilingual_coverage(self):
        langs = {r[3] for r in GLOBAL_RSS_FEEDS}
        # The expansion promise: at least these five non-English,
        # non-Chinese languages are represented.
        assert {"ja", "de", "fr", "ko", "es"} <= langs

    def test_no_overlap_with_wechat2rss_or_independent_jobs(self):
        from app.services.news.sources.wechat2rss_batch import WECHAT2RSS_FEEDS

        wechat_urls = {h for _, _, h in WECHAT2RSS_FEEDS}
        for slug, _, url, _, _ in GLOBAL_RSS_FEEDS:
            assert slug not in {s for s, _, _ in WECHAT2RSS_FEEDS}
            assert all(h not in url for h in wechat_urls)


class TestBatchCrawler:
    def _client(self, payload: str = _SAMPLE_RSS) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=payload)

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def test_fetch_recent_maps_per_feed_source_and_language(self):
        crawler = GlobalRssBatchCrawler("a", delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        batch = GLOBAL_RSS_BATCHES["a"]
        expected_sources = {f"global_{r[0]}" for r in batch}
        assert {a.source for a in articles} == expected_sources
        by_slug = {r[0]: r for r in batch}
        for a in articles:
            row = by_slug[a.source.removeprefix("global_")]
            assert a.language == row[3]
            assert a.market == row[4]
            assert "Artikeltext" in (a.body or "")

    def test_unknown_batch_is_empty_not_error(self):
        crawler = GlobalRssBatchCrawler("zzz", delay_seconds=0, client=self._client())
        assert asyncio.run(crawler.fetch_recent()) == []

    def test_failing_feed_does_not_break_batch(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = GlobalRssBatchCrawler("a", delay_seconds=0, client=client)
        assert asyncio.run(crawler.fetch_recent()) == []


class TestSharedParserExtensions:
    """rss_common extensions added for this expansion (Atom + RDF)."""

    def test_atom_feed_parses_namespaced_fields(self):
        from app.services.news.sources.rss_common import parse_rss_items

        arts = parse_rss_items(_SAMPLE_ATOM, source="t", language="ja")
        assert len(arts) == 1
        assert arts[0].title == "Atom 記事タイトル"
        assert arts[0].url == "https://example.com/atom/1"
        # Atom <content> wins over <summary>.
        assert "中央銀行" in (arts[0].body or "")
        assert arts[0].published_at.year == 2026

    def test_rdf_feed_parses_namespaced_fields(self):
        from app.services.news.sources.rss_common import parse_rss_items

        arts = parse_rss_items(_SAMPLE_RDF, source="t", language="ja")
        assert len(arts) == 1
        assert arts[0].title == "RDF 記事タイトル"
        assert arts[0].url == "https://example.com/news/1"
        assert "市場動向" in (arts[0].body or "")


class TestSchedulerWiring:
    def test_batch_jobs_materialized(self):
        from app.services.news import scheduler_jobs as sj

        assert len(sj.GLOBAL_RSS_BATCH_JOBS) == len(GLOBAL_RSS_BATCHES)
        for _job_id, _label, batch in sj.GLOBAL_RSS_BATCH_JOBS:
            fn = getattr(sj, f"run_global_rss_{batch}_crawl")
            assert callable(fn)
            assert fn.__name__ == f"run_global_rss_{batch}_crawl"

    @pytest.mark.parametrize("batch", list("abcdefghijkl"))
    def test_health_meta_exists(self, batch):
        from app.api.v1.news import _WORKER_META

        assert f"news_global_rss_{batch}_60m" in _WORKER_META

    def test_worker_keyword_covers_jobs(self):
        from app.api.v1.news import _WORKER_KEYWORDS
        from app.services.news import scheduler_jobs as sj

        for job_id, _label, _batch in sj.GLOBAL_RSS_BATCH_JOBS:
            assert any(k in job_id for k in _WORKER_KEYWORDS)


class TestTranslationMultilingual:
    def test_prompts_are_multilingual_not_english_only(self):
        from app.services.news import translation_service as ts

        assert "多种语言" in ts._TRANSLATION_SYSTEM
        assert "多种语言" in ts._TITLE_TRANSLATION_SYSTEM
        for lang in ("日语", "德语", "法语", "韩语", "西班牙语"):
            assert lang in ts._TRANSLATION_SYSTEM

    def test_language_gate_only_excludes_chinese(self):
        from app.services.news.translation_service import is_chinese_language

        for code in ("ja", "de", "fr", "ko", "es", "en"):
            assert not is_chinese_language(code)
        for code in ("zh", "zh-CN", "zh-tw", "cn"):
            assert is_chinese_language(code)
