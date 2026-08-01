"""时区处理与未来时间钳制测试（2026-08-01 生产事故回归）。

事故背景：资讯页出现"未来时间"文章。根因是 nocutnews 的 RSS
``<dc:date>`` 是韩国本地墙钟时间（KST, UTC+9）却标注 "GMT"，解析器
按字面信任时区标注后入库即比真实 UTC 快 9 小时，前端 +8 显示成未来
时间。同类问题还有 iThome 台湾的 naive 时间戳（UTC+8 被默认按 UTC）。

覆盖：
  - 带 +0900 偏移的 pubDate 正确归一化为 UTC（基线，不回归）。
  - ``tz_override``：feed 时区标注错误时按发行方本地时区重解释墙钟。
  - ``default_tz``：naive 时间戳按指定本地时区解释。
  - ``GlobalRssBatchCrawler`` 对 nocutnews 自动应用 Asia/Seoul override。
  - ``NewsNormalizer`` 入库前把超过 now+15min 的 published_at 钳到 now。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.services.news.crawler.types import RawArticle
from app.services.news.normalizer import NewsNormalizer
from app.services.news.sources.global_rss_batch import (
    GLOBAL_RSS_BATCHES,
    GLOBAL_RSS_TZ_OVERRIDE,
    GlobalRssBatchCrawler,
)
from app.services.news.sources.rss_common import parse_rss_items

KST = ZoneInfo("Asia/Seoul")
CST = ZoneInfo("Asia/Shanghai")

# 韩国 feed 标准形式：pubDate 带 +0900 偏移（donga / etnews / sbs 等）。
_RSS_KO_OFFSET = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>ko</title>
    <item>
      <title>한국 기사</title>
      <link>https://example.com/ko/1</link>
      <description>본문</description>
      <pubDate>Sat, 01 Aug 2026 22:06:42 +0900</pubDate>
    </item>
  </channel>
</rss>"""

# nocutnews 实际形态：dc:date 是 KST 墙钟时间却标注 GMT（事故现场）。
_RSS_KO_MISLABELED_GMT = """<?xml version="1.0" encoding="utf-8"?>
<rss xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
  <channel>
    <title>노컷뉴스</title>
    <item>
      <title>기사 제목</title>
      <link>https://www.nocutnews.co.kr/news/6556873</link>
      <description>본문 내용</description>
      <dc:date>Sat, 01 Aug 2026 21:06:42 GMT</dc:date>
    </item>
  </channel>
</rss>"""

# iThome 台湾实际形态：naive 本地时间（UTC+8），日期与时间间两个空格。
_RSS_TW_NAIVE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>iThome</title>
    <item>
      <title>台灣新聞</title>
      <link>https://www.ithome.com.tw/news/1</link>
      <description>內文</description>
      <pubDate>2026-08-01  10:08:56</pubDate>
    </item>
  </channel>
</rss>"""


class TestOffsetParsing:
    """基线：带正确时区标注的时间必须原样归一化为 UTC。"""

    def test_plus0900_pubdate_stored_as_utc(self):
        arts = parse_rss_items(_RSS_KO_OFFSET, source="t", language="ko")
        assert len(arts) == 1
        # 22:06:42 +0900 == 13:06:42 UTC
        assert arts[0].published_at == datetime(2026, 8, 1, 13, 6, 42, tzinfo=timezone.utc)

    def test_naive_date_uses_default_tz(self):
        arts = parse_rss_items(
            _RSS_TW_NAIVE, source="t", language="zh", default_tz=CST
        )
        assert len(arts) == 1
        # 10:08:56 +0800 == 02:08:56 UTC
        assert arts[0].published_at == datetime(2026, 8, 1, 2, 8, 56, tzinfo=timezone.utc)

    def test_naive_date_defaults_to_utc_without_default_tz(self):
        arts = parse_rss_items(_RSS_TW_NAIVE, source="t", language="zh")
        assert arts[0].published_at == datetime(2026, 8, 1, 10, 8, 56, tzinfo=timezone.utc)


class TestTzOverride:
    """时区标注错误的 feed：忽略自带标注，按本地时区重解释墙钟时间。"""

    def test_mislabeled_gmt_reinterpreted_as_seoul(self):
        arts = parse_rss_items(
            _RSS_KO_MISLABELED_GMT, source="global_nocutnews", language="ko",
            tz_override=KST,
        )
        assert len(arts) == 1
        # 墙钟 21:06:42 按 KST(+9) 解释 == 12:06:42 UTC，
        # 而不是按字面 GMT 的 21:06:42 UTC（后者就是"未来时间"的来源）。
        assert arts[0].published_at == datetime(2026, 8, 1, 12, 6, 42, tzinfo=timezone.utc)

    def test_without_override_mislabeled_gmt_passes_through(self):
        # 不加 override 时保持旧行为（按字面信任 GMT）——证明 override
        # 是修复的必要条件，也防止 override 悄悄影响正常 feed。
        arts = parse_rss_items(
            _RSS_KO_MISLABELED_GMT, source="global_nocutnews", language="ko"
        )
        assert arts[0].published_at == datetime(2026, 8, 1, 21, 6, 42, tzinfo=timezone.utc)

    def test_override_does_not_change_wall_time_only_interpretation(self):
        # override 作用于 aware 时间（GMT 标注解析后是 aware），验证
        # 重解释只换时区标注、不动墙钟时分秒。
        arts = parse_rss_items(
            _RSS_KO_OFFSET, source="t", language="ko", tz_override=KST
        )
        # 22:06:42 的墙钟按 KST 重解释 == 13:06:42 UTC（与原 +0900 一致，
        # 因为该 feed 标注本来就是对的 KST）。
        assert arts[0].published_at == datetime(2026, 8, 1, 13, 6, 42, tzinfo=timezone.utc)


class TestGlobalBatchOverrideWiring:
    """GlobalRssBatchCrawler 对命中 GLOBAL_RSS_TZ_OVERRIDE 的 slug 自动接线。"""

    def test_nocutnews_batch_applies_seoul_override(self):
        # 找到 nocutnews 所在的 batch，mock HTTP 返回误标 GMT 的 feed。
        batch_key = next(
            key
            for key, rows in GLOBAL_RSS_BATCHES.items()
            if any(r[0] == "nocutnews" for r in rows)
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_RSS_KO_MISLABELED_GMT)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = GlobalRssBatchCrawler(batch_key, delay_seconds=0, client=client)
        articles = asyncio.run(crawler.fetch_recent())
        nocut = [a for a in articles if a.source == "global_nocutnews"]
        assert len(nocut) == 1
        assert nocut[0].published_at == datetime(
            2026, 8, 1, 12, 6, 42, tzinfo=timezone.utc
        )

    def test_override_table_slugs_exist_in_feed_table(self):
        from app.services.news.sources.global_rss_batch import GLOBAL_RSS_FEEDS

        slugs = {r[0] for r in GLOBAL_RSS_FEEDS}
        for slug in GLOBAL_RSS_TZ_OVERRIDE:
            assert slug in slugs


# ---------------------------------------------------------------------------
# Normalizer 未来时间钳制
# ---------------------------------------------------------------------------


@pytest.fixture
def news_db():
    """Fresh in-memory SQLite（与 test_news.py 同款 fixture 模式）。"""
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _raw_with_ts(ts: datetime, *, source_id: str = "tz-1") -> RawArticle:
    return RawArticle(
        source="global_nocutnews",
        source_id=source_id,
        url=f"https://example.com/{source_id}",
        title="테스트 기사",
        body="본문",
        published_at=ts,
        language="ko",
        market="us",
    )


class TestFutureClamp:
    def test_far_future_published_at_clamped_to_now(self, news_db):
        now = datetime.now(tz=timezone.utc)
        raw = _raw_with_ts(now + timedelta(hours=9))  # nocutnews 事故形态
        article = NewsNormalizer(news_db).normalize(raw)
        assert article is not None
        # 钳到 now（SQLite 存 naive，比较前统一 naive UTC）。
        stored = article.published_at.replace(tzinfo=timezone.utc)
        assert abs((stored - now).total_seconds()) < 60

    def test_within_tolerance_not_clamped(self, news_db):
        now = datetime.now(tz=timezone.utc)
        # 10 分钟 < 15 分钟容忍窗口：CMS 时钟漂移/定时发布，原样保留。
        ts = now + timedelta(minutes=10)
        raw = _raw_with_ts(ts, source_id="tz-2")
        article = NewsNormalizer(news_db).normalize(raw)
        assert article is not None
        stored = article.published_at.replace(tzinfo=timezone.utc)
        assert abs((stored - ts).total_seconds()) < 2

    def test_past_published_at_untouched(self, news_db):
        ts = datetime(2026, 8, 1, 12, 6, 42, tzinfo=timezone.utc)
        raw = _raw_with_ts(ts, source_id="tz-3")
        article = NewsNormalizer(news_db).normalize(raw)
        assert article is not None
        stored = article.published_at.replace(tzinfo=timezone.utc)
        assert stored == ts
