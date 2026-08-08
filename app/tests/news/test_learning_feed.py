"""学习中心后端测试（2026-08-02）。

Coverage:
  - NewsSourceMeta 模型 CRUD（SQLite 内存库）。
  - 种子数据：幂等（重复执行 0 插入）、slug 全部能在批次表/rss_simple
    里找到（防手滑打错 source）、content_type/topic/difficulty 取值合法。
  - ``GET /api/v1/learning/feed``：只返回打标源、近 N 天窗口、
    topic/content_type 过滤、importance 优先排序、分页、参数校验。
  - ``GET /api/v1/learning/topics``：各主题计数 + 零计数主题也返回。
  - wechat batch2/3 category 落库链路：crawler → extra["category"] →
    normalizer._derive_category → news_article.category。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.news_source_meta import (
    CONTENT_TYPES,
    DIFFICULTIES,
    TOPICS,
    NewsSourceMeta,
)
from app.services.news._model_loader import NewsArticle
from app.services.news.source_meta_seed import SOURCE_META_SEED, seed_source_meta

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def learning_db():
    """Fresh in-memory SQLite with all tables (StaticPool for threads)."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # 显式注册 UserArticleState：单独跑本文件时没有别的模块 import 它，
    # create_all 只会建已注册进 Base.metadata 的表（全量跑时靠测试顺序侥幸通过）。
    from app.models.user_article_state import UserArticleState  # noqa: F401

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _add_article(
    db,
    *,
    source: str,
    source_id: str,
    published_at: datetime,
    importance: int | None = None,
    title: str = "t",
) -> NewsArticle:
    row = NewsArticle(
        source=source,
        source_id=source_id,
        url=f"https://example.com/{source}/{source_id}",
        url_hash=f"hash-{source}-{source_id}",
        title=title,
        summary="s",
        language="zh",
        market="cn_a",
        published_at=published_at,
        importance=importance,
    )
    db.add(row)
    return row


def _add_meta(
    db,
    *,
    source: str,
    content_type: str = "deep",
    topic: str = "macro",
    difficulty: str | None = None,
) -> NewsSourceMeta:
    row = NewsSourceMeta(
        source=source,
        content_type=content_type,
        topic=topic,
        difficulty_default=difficulty,
        display_group="测试组",
        note="测试源",
    )
    db.add(row)
    return row


class _FakeUser:
    """A stand-in for the JWT-auth user."""

    id = 1  # P1 起 feed 用 user.id LEFT JOIN user_article_state
    username = "tester"
    role = "user"


@pytest.fixture
def api_client(learning_db):
    """TestClient mounting only the learning router against ``learning_db``."""
    from fastapi import FastAPI

    from app.api.v1 import learning as learning_module

    def _override_db():
        try:
            yield learning_db
        finally:
            pass

    def _override_user():
        return _FakeUser()

    test_app = FastAPI()
    test_app.include_router(learning_module.router, prefix="/api/v1/learning")
    test_app.dependency_overrides[learning_module.get_db] = _override_db
    test_app.dependency_overrides[learning_module.get_current_user] = _override_user
    with TestClient(test_app) as client:
        yield client
    test_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 模型 CRUD
# ---------------------------------------------------------------------------

class TestSourceMetaCRUD:
    def test_insert_and_read(self, learning_db):
        _add_meta(
            learning_db,
            source="wechat_zepinghongguan",
            content_type="deep",
            topic="macro",
            difficulty="advanced",
        )
        learning_db.commit()
        row = learning_db.get(NewsSourceMeta, "wechat_zepinghongguan")
        assert row is not None
        assert row.content_type == "deep"
        assert row.topic == "macro"
        assert row.difficulty_default == "advanced"

    def test_nullable_fields(self, learning_db):
        # topic / difficulty / display_group / note 均可空
        row = NewsSourceMeta(source="s1", content_type="deep")
        learning_db.add(row)
        learning_db.commit()
        got = learning_db.get(NewsSourceMeta, "s1")
        assert got.topic is None
        assert got.difficulty_default is None


# ---------------------------------------------------------------------------
# 种子数据
# ---------------------------------------------------------------------------

class TestSeed:
    def test_seed_values_legal(self):
        """种子行的 content_type/topic/difficulty 必须落在合法取值内。"""
        for row in SOURCE_META_SEED:
            assert row["content_type"] in CONTENT_TYPES, row
            assert row["topic"] in TOPICS, row
            assert row["difficulty_default"] in DIFFICULTIES + (None,), row

    def test_seed_sources_unique(self):
        sources = [r["source"] for r in SOURCE_META_SEED]
        assert len(sources) == len(set(sources))

    def test_seed_sources_exist_in_batch_tables(self):
        """每个种子 slug 都要能在批次表 / rss_simple / wewe-rss 已知
        账号里找到——防手滑打错 source（打错了 join 永远为空）。"""
        import inspect

        import app.services.news.sources.rss_simple as rs
        from app.services.news.sources.ai_cn_batch import AI_CN_FEEDS
        from app.services.news.sources.ai_us_batch import AI_US_FEEDS
        from app.services.news.sources.asia_en_batch import ASIA_EN_FEEDS
        from app.services.news.sources.edu_batch import EDU_FEEDS
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

        known: set[str] = set()
        known |= {f"wechat_{r[0]}" for r in WECHAT2RSS_FEEDS}
        known |= {f"wechat_{r[0]}" for r in WECHAT2B_FEEDS}
        known |= {f"wechat_{r[0]}" for r in WECHAT3_FEEDS}
        known |= {f"zhx_{r[0]}" for r in ZH_MULTI_FEEDS}
        known |= {f"zhb_{r[0]}" for r in ZH_BLOG_FEEDS}
        known |= {f"indie_{r[0]}" for r in INDEPENDENT_FEEDS}
        known |= {f"gind_{r[0]}" for r in GLOBAL_INDIE_FEEDS}
        known |= {f"global_{r[0]}" for r in GLOBAL_RSS_FEEDS}
        # asen 批次 slug 自带 asen_ 前缀
        known |= {r[0] for r in ASIA_EN_FEEDS}
        # edu 科普批次（2026-08-02）：source = edu_{slug}
        known |= {f"edu_{r[0]}" for r in EDU_FEEDS}
        # 2026-08-02 三波扩源批次表：source = {enf,ofc,zhm}_{slug}
        known |= {f"enf_{r[0]}" for r in EN_FIN_FEEDS}
        known |= {f"ofc_{r[0]}" for r in OFFICIAL_FEEDS}
        known |= {f"zhm_{r[0]}" for r in ZH_MEDIA_FEEDS}
        # AI 产业链批次（2026-08-04）：slug 自带完整前缀（wechat_/gind_/pod_ 等）
        known |= {r[0] for r in AI_CN_FEEDS}
        known |= {r[0] for r in AI_US_FEEDS}
        for _, cls in inspect.getmembers(rs, inspect.isclass):
            sn = getattr(cls, "source_name", None)
            if sn and cls.__module__ == rs.__name__:
                known.add(sn)
        # wewe-rss 账号（env 配置的 WECHAT_RSS_FEED_MAP，见 batch2 docstring）
        known |= {
            "wechat_zhigu", "wechat_yuanchuan", "wechat_canghai",
            "wechat_fupeng", "wechat_lixunlei", "wechat_congming",
            "wechat_beiwei", "wechat_latepost", "wechat_zeping",
        }

        unknown = [r["source"] for r in SOURCE_META_SEED if r["source"] not in known]
        assert unknown == []

    def test_seed_idempotent(self, learning_db):
        first = seed_source_meta(learning_db)
        assert first == len(SOURCE_META_SEED)
        second = seed_source_meta(learning_db)
        assert second == 0
        total = learning_db.execute(
            select(NewsSourceMeta.source)
        ).scalars().all()
        assert len(total) == len(SOURCE_META_SEED)


# ---------------------------------------------------------------------------
# GET /learning/feed
# ---------------------------------------------------------------------------

@pytest.fixture
def seeded_db(learning_db):
    """两打标源 + 一未打标源的文章，覆盖过滤/排序/窗口分支。"""
    now = datetime.now(tz=UTC).replace(tzinfo=None)
    _add_meta(learning_db, source="deep_macro", content_type="deep", topic="macro")
    _add_meta(learning_db, source="edu_alloc", content_type="edu", topic="allocation", difficulty="beginner")
    # 未打标源（快讯）——绝不能出现在 feed 里
    _add_article(learning_db, source="flash_news", source_id="f1", published_at=now, importance=5)
    # 打标源文章
    _add_article(learning_db, source="deep_macro", source_id="m1", published_at=now - timedelta(days=1), importance=None)
    _add_article(learning_db, source="deep_macro", source_id="m2", published_at=now - timedelta(days=2), importance=5)
    _add_article(learning_db, source="deep_macro", source_id="m3", published_at=now - timedelta(days=3), importance=3)
    _add_article(learning_db, source="edu_alloc", source_id="a1", published_at=now - timedelta(days=1), importance=4)
    # 窗口外（默认 90 天）
    _add_article(learning_db, source="deep_macro", source_id="old", published_at=now - timedelta(days=120), importance=5)
    learning_db.commit()
    return learning_db


class TestLearningFeed:
    def test_only_tagged_sources_in_window(self, api_client, seeded_db):
        resp = api_client.get("/api/v1/learning/feed")
        assert resp.status_code == 200
        data = resp.json()
        sources = {item["source"] for item in data["items"]}
        assert "flash_news" not in sources  # 未打标源不出现
        ids = {item["source_id"] for item in data["items"]}
        assert "old" not in ids  # 90 天窗口外不出现
        assert data["total"] == 4

    def test_importance_first_ordering(self, api_client, seeded_db):
        data = api_client.get("/api/v1/learning/feed").json()
        items = data["items"]
        # importance DESC NULLS LAST：5 → 4 → 3 → NULL
        got = [(i["source_id"], i["importance"]) for i in items]
        assert got == [("m2", 5), ("a1", 4), ("m3", 3), ("m1", None)]

    def test_item_shape(self, api_client, seeded_db):
        data = api_client.get("/api/v1/learning/feed").json()
        item = data["items"][0]
        # 与 /news 列表项一致的字段
        for key in ("id", "source", "url", "title", "title_zh", "summary_zh",
                    "published_at", "market", "symbols"):
            assert key in item
        # 学习维度附加字段
        assert item["content_type"] == "deep"
        assert item["topic"] == "macro"
        assert "difficulty_default" in item
        assert "importance" in item

    def test_topic_filter(self, api_client, seeded_db):
        data = api_client.get("/api/v1/learning/feed", params={"topic": "allocation"}).json()
        assert data["total"] == 1
        assert data["items"][0]["source"] == "edu_alloc"
        assert data["items"][0]["content_type"] == "edu"
        assert data["items"][0]["difficulty_default"] == "beginner"

    def test_content_type_filter(self, api_client, seeded_db):
        data = api_client.get("/api/v1/learning/feed", params={"content_type": "edu"}).json()
        assert data["total"] == 1
        assert data["items"][0]["source"] == "edu_alloc"

    def test_days_window(self, api_client, seeded_db):
        # days=2 只留 m1/a1（m2/m3 在 2 天外）
        data = api_client.get("/api/v1/learning/feed", params={"days": 2}).json()
        assert data["total"] == 2

    def test_pagination(self, api_client, seeded_db):
        page1 = api_client.get(
            "/api/v1/learning/feed", params={"page": 1, "page_size": 3}
        ).json()
        page2 = api_client.get(
            "/api/v1/learning/feed", params={"page": 2, "page_size": 3}
        ).json()
        assert page1["total"] == 4
        assert page1["total_pages"] == 2
        assert len(page1["items"]) == 3
        assert len(page2["items"]) == 1
        ids1 = {i["id"] for i in page1["items"]}
        ids2 = {i["id"] for i in page2["items"]}
        assert ids1.isdisjoint(ids2)

    def test_invalid_topic_rejected(self, api_client, seeded_db):
        resp = api_client.get("/api/v1/learning/feed", params={"topic": "nonsense"})
        assert resp.status_code == 400

    def test_invalid_content_type_rejected(self, api_client, seeded_db):
        resp = api_client.get(
            "/api/v1/learning/feed", params={"content_type": "flash"}
        )
        assert resp.status_code == 400

    def test_difficulty_filter(self, api_client, seeded_db):
        """P2：difficulty=beginner 只留 beginner 源的文章；NULL 难度源被排除。"""
        data = api_client.get(
            "/api/v1/learning/feed", params={"difficulty": "beginner"}
        ).json()
        assert data["total"] == 1
        assert data["items"][0]["source"] == "edu_alloc"
        assert data["items"][0]["difficulty_default"] == "beginner"
        # seeded_db 没有 advanced 源 → 空列表而不是报错
        data = api_client.get(
            "/api/v1/learning/feed", params={"difficulty": "advanced"}
        ).json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_difficulty_combines_with_topic(self, api_client, seeded_db):
        data = api_client.get(
            "/api/v1/learning/feed",
            params={"topic": "allocation", "difficulty": "beginner"},
        ).json()
        assert data["total"] == 1
        # 组合条件不匹配时为空
        data = api_client.get(
            "/api/v1/learning/feed",
            params={"topic": "macro", "difficulty": "beginner"},
        ).json()
        assert data["total"] == 0

    def test_invalid_difficulty_rejected(self, api_client, seeded_db):
        resp = api_client.get(
            "/api/v1/learning/feed", params={"difficulty": "expert"}
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /learning/topics
# ---------------------------------------------------------------------------

class TestLearningTopics:
    def test_topic_counts(self, api_client, seeded_db):
        resp = api_client.get("/api/v1/learning/topics")
        assert resp.status_code == 200
        data = resp.json()
        counts = {t["topic"]: t["count"] for t in data["topics"]}
        # deep_macro 窗口内 3 篇，edu_alloc 1 篇；未打标源不计
        assert counts["macro"] == 3
        assert counts["allocation"] == 1
        assert data["total"] == 4

    def test_all_topics_present(self, api_client, seeded_db):
        data = api_client.get("/api/v1/learning/topics").json()
        topics = [t["topic"] for t in data["topics"]]
        assert topics == list(TOPICS)
        # 零计数主题也返回 0（Tab 列表稳定）
        counts = {t["topic"]: t["count"] for t in data["topics"]}
        assert counts["psychology"] == 0

    def test_days_param(self, api_client, seeded_db):
        data = api_client.get("/api/v1/learning/topics", params={"days": 2}).json()
        counts = {t["topic"]: t["count"] for t in data["topics"]}
        assert counts["macro"] == 1  # 只有 m1 在 2 天窗口内
        assert counts["allocation"] == 1


# ---------------------------------------------------------------------------
# wechat batch2/3 category 落库链路
# ---------------------------------------------------------------------------

class TestWechatCategoryPersisted:
    _RSS = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
      <title>t</title>
      <item>
        <title>文章一</title>
        <link>https://mp.weixin.qq.com/s/abc1</link>
        <guid>https://mp.weixin.qq.com/s/abc1</guid>
        <description>正文</description>
        <pubDate>Wed, 29 Jul 2026 08:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """

    def test_parse_rss_items_default_category(self):
        """条目自身无 <category> 时，回落到源级 default_category。"""
        from app.services.news.sources.rss_common import parse_rss_items

        rows = parse_rss_items(
            self._RSS, source="wechat_x", default_category="macro"
        )
        assert len(rows) == 1
        assert rows[0].extra["category"] == "macro"

    def test_item_category_wins_over_default(self):
        """条目自带 <category> 时不被 default_category 覆盖。"""
        from app.services.news.sources.rss_common import parse_rss_items

        xml = self._RSS.replace("<description>正文</description>",
                                "<description>正文</description><category>own</category>")
        rows = parse_rss_items(
            xml, source="wechat_x", default_category="macro"
        )
        assert rows[0].extra["category"] == "own"

    def test_no_default_no_category(self):
        from app.services.news.sources.rss_common import parse_rss_items

        rows = parse_rss_items(self._RSS, source="wechat_x")
        assert rows[0].extra == {}

    @pytest.mark.asyncio
    async def test_batch2_crawler_passes_category(self, monkeypatch):
        """batch2 crawler 把行内 category 传进 parse_rss_items。"""
        import httpx

        from app.services.news.sources.wechat2rss_batch2 import (
            WECHAT2B_BATCHES,
            Wechat2RssBatch2Crawler,
        )

        batch_key = sorted(WECHAT2B_BATCHES)[0]
        expected_categories = [row[2] for row in WECHAT2B_BATCHES[batch_key]]

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, text=self._RSS)
        )
        async with httpx.AsyncClient(transport=transport) as client:
            crawler = Wechat2RssBatch2Crawler(
                batch_key, delay_seconds=0, client=client
            )
            articles = await crawler.fetch_recent()

        assert len(articles) == len(expected_categories)
        got = {a.extra.get("category") for a in articles}
        assert got == set(expected_categories)
        assert all(a.source.startswith("wechat_") for a in articles)

    def test_derive_category_reads_extra(self):
        """normalizer._derive_category 认 extra[\"category\"]（链路末端）。"""
        from app.services.news.crawler.types import RawArticle
        from app.services.news.normalizer import _derive_category

        raw = RawArticle(
            source="wechat_zepinghongguan",
            url="https://example.com/1",
            title="t",
            published_at=datetime.now(tz=UTC),
            extra={"category": "macro"},
        )
        assert _derive_category(raw) == "macro"
