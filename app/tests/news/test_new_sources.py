"""Tests for the international & official news sources added 2026-07-21.

Coverage:
  - ``SimpleRssCrawler`` subclasses: ``parse_rss_items`` handles a
    representative inline RSS sample per source (no network).
  - ``ClsCrawler``: JSON telegraph payload parsing, plus the two
    defensive paths (non-zero ``errno`` and WAF HTML responses).
  - Persistence: parsed articles from each source go through
    ``NewsNormalizer`` into the in-memory SQLite schema with the
    correct ``source`` field (uses the shared ``db_session`` fixture).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

from app.services.news.crawler.base import _Response
from app.services.news.normalizer import NewsNormalizer
from app.services.news.sources.cls import ClsCrawler
from app.services.news.sources.rss_simple import (
    ArxivQfinCrawler,
    BankOfEnglandCrawler,
    BbcBusinessCrawler,
    DecryptCrawler,
    EcbCrawler,
    FederalReserveCrawler,
    FtCrawler,
    InvestingCrawler,
    MarketWatchCrawler,
    SeekingAlphaCrawler,
    SimpleRssCrawler,
    ZeroHedgeCrawler,
)


def _fake_response(text: str) -> _Response:
    return _Response(
        url="test://",
        text=text,
        content=text.encode("utf-8"),
        status_code=200,
        headers={},
    )


_RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample Feed</title>
    <item>
      <title>Fed holds rates steady in July meeting</title>
      <link>https://example.com/article-1</link>
      <guid>https://example.com/article-1</guid>
      <pubDate>Tue, 21 Jul 2026 14:00:00 GMT</pubDate>
      <description>The central bank kept its benchmark rate unchanged.</description>
    </item>
    <item>
      <title>Missing link placeholder</title>
    </item>
  </channel>
</rss>"""

_ARXIV_SAMPLE = """<?xml version='1.0' encoding='UTF-8'?>
<rss xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
  <channel>
    <title>q-fin updates on arXiv.org</title>
    <item>
      <title>Deep Hedging under Market Impact</title>
      <link>https://arxiv.org/abs/2607.12345</link>
      <description>arXiv:2607.12345v1 Announce Type: new Abstract: We study deep hedging.</description>
      <dc:creator>Smith, John</dc:creator>
      <pubDate>Tue, 21 Jul 2026 00:00:00 -0400</pubDate>
      <guid>https://arxiv.org/abs/2607.12345</guid>
    </item>
  </channel>
</rss>"""


class TestSimpleRssSources:
    """Each RSS subclass parses a sample feed and tags articles correctly."""

    RSS_CRAWLERS = [
        (MarketWatchCrawler, "marketwatch", "us", "MarketWatch"),
        (ZeroHedgeCrawler, "zerohedge", "us", "ZeroHedge"),
        (SeekingAlphaCrawler, "seekingalpha", "us", "Seeking Alpha"),
        (FtCrawler, "ft", "us", "Financial Times"),
        (InvestingCrawler, "investing", "us", "Investing.com"),
        (DecryptCrawler, "decrypt", "crypto", "Decrypt"),
        (FederalReserveCrawler, "federal_reserve", "us", "Federal Reserve"),
        (EcbCrawler, "ecb", "us", "ECB"),
        (BankOfEnglandCrawler, "bankofengland", "us", "Bank of England"),
        (BbcBusinessCrawler, "bbc_business", "us", "BBC"),
    ]

    @pytest.mark.parametrize(
        "crawler_cls,source_name,market,author",
        RSS_CRAWLERS,
        ids=lambda v: v if isinstance(v, str) else None,
    )
    def test_parses_rss_sample(self, crawler_cls, source_name, market, author):
        crawler = crawler_cls()
        articles = asyncio.run(crawler.parse(_fake_response(_RSS_SAMPLE)))
        assert len(articles) == 1
        a = articles[0]
        assert a.source == source_name
        assert a.market == market
        assert a.language == "en"
        assert a.author == author
        assert a.url == "https://example.com/article-1"
        assert a.source_id == "https://example.com/article-1"
        assert a.published_at.tzinfo is not None
        assert "Fed holds rates" in a.title

    def test_arxiv_parses_sample(self):
        crawler = ArxivQfinCrawler()
        articles = asyncio.run(crawler.parse(_fake_response(_ARXIV_SAMPLE)))
        assert len(articles) == 1
        a = articles[0]
        assert a.source == "arxiv_qfin"
        assert a.market == "us"
        assert a.author == "Smith, John"
        assert a.url == "https://arxiv.org/abs/2607.12345"
        assert "Deep Hedging" in a.title

    def test_broken_xml_returns_empty(self):
        crawler = MarketWatchCrawler()
        assert asyncio.run(crawler.parse(_fake_response("not xml"))) == []

    def test_base_class_has_no_feed_url(self):
        # The parameterised base must not be registered as a real source.
        assert SimpleRssCrawler.feed_url == ""


class TestClsCrawler:
    def _payload(self, **overrides) -> str:
        data = {
            "errno": 0,
            "data": {
                "roll_data": [
                    {
                        "id": 2433191,
                        "type": -1,
                        "title": "央行开展 500 亿元逆回购操作",
                        "brief": "中国人民银行今日开展 500 亿元 7 天期逆回购操作。",
                        "content": "<p>中国人民银行今日开展 500 亿元 7 天期逆回购操作。</p>",
                        "ctime": "1753108800",
                    },
                    {
                        "id": 2433192,
                        "type": 0,
                        "title": "",
                        "brief": "只有摘要的快讯，没有标题。",
                        "content": "",
                        "ctime": "1753108860",
                    },
                ]
            },
        }
        data.update(overrides)
        return json.dumps(data, ensure_ascii=False)

    def test_parses_telegraph_payload(self):
        crawler = ClsCrawler()
        articles = asyncio.run(crawler.parse(_fake_response(self._payload())))
        assert len(articles) == 2

        a = articles[0]
        assert a.source == "cls"
        assert a.market == "cn_a"
        assert a.language == "zh"
        assert a.source_id == "2433191"
        assert a.url == "https://www.cls.cn/detail/2433191"
        assert a.author == "财联社"
        # ctime is unix seconds -> tz-aware datetime.
        assert a.published_at == datetime(2025, 7, 21, 14, 40, tzinfo=timezone.utc)
        # Body is HTML-stripped; raw HTML kept in body_html.
        assert a.body is not None and "<p>" not in a.body
        assert a.body_html is not None and "<p>" in a.body_html

        # Second item has no title -> brief truncated to a fallback title.
        b = articles[1]
        assert b.title.startswith("只有摘要的快讯")
        assert b.url == "https://www.cls.cn/detail/2433192"

    def test_nonzero_errno_returns_empty(self):
        crawler = ClsCrawler()
        payload = json.dumps({"errno": 1001, "msg": "blocked", "data": {}})
        assert asyncio.run(crawler.parse(_fake_response(payload))) == []

    def test_waf_html_returns_empty(self):
        crawler = ClsCrawler()
        html = "<html><head><title>CloudWAF</title></head><body>verify</body></html>"
        assert asyncio.run(crawler.parse(_fake_response(html))) == []

    def test_invalid_json_returns_empty(self):
        crawler = ClsCrawler()
        assert asyncio.run(crawler.parse(_fake_response("{not json"))) == []


class TestNewSourcesPersistence:
    """Parsed articles normalize + persist with the right source field."""

    @pytest.mark.parametrize(
        "crawler_cls,source_name",
        [
            (MarketWatchCrawler, "marketwatch"),
            (DecryptCrawler, "decrypt"),
            (FederalReserveCrawler, "federal_reserve"),
            (ArxivQfinCrawler, "arxiv_qfin"),
        ],
        ids=lambda v: v if isinstance(v, str) else None,
    )
    def test_rss_article_persists(self, db_session, crawler_cls, source_name):
        sample = _ARXIV_SAMPLE if source_name == "arxiv_qfin" else _RSS_SAMPLE
        crawler = crawler_cls()
        articles = asyncio.run(crawler.parse(_fake_response(sample)))
        assert articles

        normalizer = NewsNormalizer(db_session)
        article = normalizer.normalize(articles[0])
        assert article is not None
        db_session.commit()
        assert article.id is not None
        assert article.source == source_name

    def test_cls_article_persists(self, db_session):
        crawler = ClsCrawler()
        payload = json.dumps(
            {
                "errno": 0,
                "data": {
                    "roll_data": [
                        {
                            "id": 9990001,
                            "type": -1,
                            "title": "沪深两市成交额突破万亿",
                            "brief": "沪深两市成交额突破 1 万亿元。",
                            "content": "",
                            "ctime": "1753108800",
                        }
                    ]
                },
            },
            ensure_ascii=False,
        )
        articles = asyncio.run(crawler.parse(_fake_response(payload)))
        assert len(articles) == 1

        normalizer = NewsNormalizer(db_session)
        article = normalizer.normalize(articles[0])
        assert article is not None
        db_session.commit()
        assert article.id is not None
        assert article.source == "cls"
        assert article.market == "cn_a"
