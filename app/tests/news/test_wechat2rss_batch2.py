"""Tests for the second WeChat-OA batch crawler (2026-07-28).

Covers:
  - The feed table has unique slugs/URLs, well-formed slugs, valid
    categories, and >=100 sources (the /goal requirement).
  - No overlap with the first wechat2rss batch, the single-feed
    WeChat crawlers, or the wewe-rss feed-map slugs.
  - Batches partition the table completely (keys ``w2a`` …).
  - ``Wechat2RssBatch2Crawler`` parses feeds into per-source articles
    with a mocked HTTP layer.
  - Integration: batch jobs materialize in ``scheduler_jobs`` and are
    wired into the health-grid metadata (only when the integration
    patch from docs/dev-notes/20260728-wechat-batch2-integration.md
    has been applied — those tests are marked and skip otherwise).
"""

from __future__ import annotations

import asyncio
import re

import httpx
import pytest

from app.services.news.sources.wechat2rss_batch2 import (
    CATEGORIES,
    MIRROR_BESTBLOGS,
    MIRROR_XLAB,
    WECHAT2B_BATCHES,
    WECHAT2B_FEEDS,
    Wechat2RssBatch2Crawler,
)

# Names that must never appear in the table — state media / party
# outlets and pure-PR corporate accounts (user requirement: no pure
# marketing / clickbait / advertorial accounts).
_FORBIDDEN = (
    "人民日报", "新华社", "央视", "环球时报", "央广网", "人民网",
    "半月谈", "南京发布", "网信中国", "网信北京", "公安部",
)

_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>{name}</title>
    <item>
      <title>下半年宏观展望</title>
      <link>https://mp.weixin.qq.com/s?__biz=AAAA&amp;mid=1&amp;idx=1&amp;sn=x</link>
      <description>摘要一段。</description>
      <content:encoded>&lt;p&gt;这是正文全文，足够长以通过正文校验。&lt;/p&gt;</content:encoded>
      <pubDate>Mon, 27 Jul 2026 07:46:40 +0800</pubDate>
    </item>
  </channel>
</rss>"""

_BATCH_KEYS = list(WECHAT2B_BATCHES.keys())


class TestFeedTable:
    def test_unique_slugs_and_urls(self):
        slugs = [s for s, *_ in WECHAT2B_FEEDS]
        urls = [u for *_, u in WECHAT2B_FEEDS]
        assert len(slugs) == len(set(slugs))
        assert len(urls) == len(set(urls))

    def test_slug_format(self):
        for s, *_ in WECHAT2B_FEEDS:
            assert re.fullmatch(r"[a-z0-9]+", s), f"bad slug {s}"

    def test_categories_valid(self):
        for _, _, cat, _ in WECHAT2B_FEEDS:
            assert cat in CATEGORIES

    def test_every_category_nonempty(self):
        cats = {c for _, _, c, _ in WECHAT2B_FEEDS}
        assert cats == set(CATEGORIES)

    def test_no_state_or_pr_sources(self):
        for _, name, *_ in WECHAT2B_FEEDS:
            for bad in _FORBIDDEN:
                assert bad not in name, f"{name} looks official/PR"

    def test_urls_are_https_mirror_feeds(self):
        for *_, url in WECHAT2B_FEEDS:
            assert url.startswith(
                (f"{MIRROR_XLAB}/feed/", f"{MIRROR_BESTBLOGS}/feed/")
            ), f"unexpected feed host {url}"
            assert url.endswith(".xml")
            hash_part = url.rsplit("/", 1)[-1].removesuffix(".xml")
            assert re.fullmatch(r"[0-9a-f]{40}", hash_part)

    def test_batches_partition_table(self):
        flat = [row for batch in WECHAT2B_BATCHES.values() for row in batch]
        assert flat == WECHAT2B_FEEDS

    def test_batch_keys_prefixed(self):
        for key in WECHAT2B_BATCHES:
            assert re.fullmatch(r"w2[a-z]", key), f"bad batch key {key}"

    def test_at_least_100_sources(self):
        assert len(WECHAT2B_FEEDS) >= 100

    def test_no_overlap_with_wechat2rss_batch1(self):
        from app.services.news.sources.wechat2rss_batch import WECHAT2RSS_FEEDS

        b1_slugs = {s for s, _, _ in WECHAT2RSS_FEEDS}
        b1_names = {n for _, n, _ in WECHAT2RSS_FEEDS}
        b1_hashes = {h for _, _, h in WECHAT2RSS_FEEDS}
        for slug, name, _, url in WECHAT2B_FEEDS:
            assert slug not in b1_slugs, f"slug {slug} collides with batch1"
            assert name not in b1_names, f"name {name} collides with batch1"
        # A feed hash reused on the other mirror is still the same account.
        for *_, url in WECHAT2B_FEEDS:
            hash_part = url.rsplit("/", 1)[-1].removesuffix(".xml")
            assert hash_part not in b1_hashes

    def test_no_overlap_with_existing_wechat_sources(self):
        # Single-feed crawlers (rss_simple.py) and the wewe-rss
        # WECHAT_RSS_FEED_MAP slugs configured on ECS (see the
        # 20260727 runbook).
        taken = {
            "maobidao", "sixianggangyin", "zeping",
            "zhigu", "yuanchuan", "canghai", "fupeng",
            "lixunlei", "congming", "beiwei", "latepost",
        }
        for slug, name, *_ in WECHAT2B_FEEDS:
            assert slug not in taken, f"slug {slug} already in use"
        taken_names = {
            "猫笔刀", "思想钢印", "智谷趋势", "远川研究所", "沧海一土狗",
            "付鹏的财经世界", "李迅雷金融与投资", "聪明投资者",
            "北纬的日常", "晚点LatePost",
        }
        for _, name, *_ in WECHAT2B_FEEDS:
            assert name not in taken_names, f"account {name} already covered"


class TestBatchCrawler:
    def _client(self) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_SAMPLE.format(name="测试源"))

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def test_fetch_recent_maps_per_feed_source(self):
        crawler = Wechat2RssBatch2Crawler("w2a", delay_seconds=0, client=self._client())
        articles = asyncio.run(crawler.fetch_recent())
        expected = {f"wechat_{s}" for s, *_ in WECHAT2B_BATCHES["w2a"]}
        assert {a.source for a in articles} == expected
        for a in articles:
            assert a.market == "cn_a"
            assert a.language == "zh"
            assert "正文全文" in (a.body_html or a.body or "")

    def test_unknown_batch_is_empty_not_error(self):
        crawler = Wechat2RssBatch2Crawler("w2zzz", delay_seconds=0, client=self._client())
        assert asyncio.run(crawler.fetch_recent()) == []

    def test_failing_feed_does_not_break_batch(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = Wechat2RssBatch2Crawler("w2a", delay_seconds=0, client=client)
        assert asyncio.run(crawler.fetch_recent()) == []


class TestSchedulerWiring:
    """These only pass once the integration patch in
    docs/dev-notes/20260728-wechat-batch2-integration.md is applied
    to scheduler_jobs.py / scheduler.py / news.py. Until then they
    xfail so this module can land independently."""

    def test_batch_jobs_materialized(self):
        sj = pytest.importorskip("app.services.news.scheduler_jobs")
        jobs = getattr(sj, "WECHAT2B_BATCH_JOBS", None)
        if jobs is None:
            pytest.xfail("integration patch not applied yet")
        for _job_id, _label, batch in jobs:
            fn = getattr(sj, f"run_wechat2b_{batch}_crawl")
            assert callable(fn)
            assert fn.__name__ == f"run_wechat2b_{batch}_crawl"

    def test_job_table_covers_all_batches(self):
        sj = pytest.importorskip("app.services.news.scheduler_jobs")
        jobs = getattr(sj, "WECHAT2B_BATCH_JOBS", None)
        if jobs is None:
            pytest.xfail("integration patch not applied yet")
        assert {b for _, _, b in jobs} == set(_BATCH_KEYS)

    @pytest.mark.parametrize("batch", _BATCH_KEYS)
    def test_health_meta_exists(self, batch):
        try:
            from app.api.v1.news import _WORKER_META
        except ImportError:  # pragma: no cover
            pytest.skip("news api not importable")
        if f"news_wechat2b_{batch}_60m" not in _WORKER_META:
            pytest.xfail("integration patch not applied yet")

    def test_health_keyword_covers_job_ids(self):
        try:
            from app.api.v1.news import _WORKER_KEYWORDS
        except ImportError:  # pragma: no cover
            pytest.skip("news api not importable")
        if not any(k in "news_wechat2b_w2a_60m" for k in _WORKER_KEYWORDS):
            pytest.xfail("integration patch not applied yet")
