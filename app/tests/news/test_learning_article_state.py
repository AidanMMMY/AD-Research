"""学习中心 P1 测试：文章级收藏（稍后读）+ 已读标记（2026-08-02）。

Coverage:
  - UserArticleState 模型 CRUD（SQLite 内存库）：复合主键、可空时间戳。
  - 迁移脚本 ``x5y7z9a1b3c5``：revision 链挂在 ``w4x6y8z0a2b4`` 之后、
    模型与迁移的表结构不漂移（列/PK/FK 断言）。
    真库 upgrade/downgrade 往返已在本地 postgres 手动验证
    （upgrade → \\d → downgrade → to_regclass NULL → 再 upgrade）。
  - ``POST /learning/articles/{id}/bookmark``：切换语义、幂等、
    取消后已读保留、404。
  - ``POST /learning/articles/{id}/read``：幂等、不改写首次时间戳、404。
  - ``GET /learning/feed``：每项带 bookmarked/read 布尔、只反映
    当前用户的状态（别的用户的状态不泄漏）。
  - ``GET /learning/bookmarks``：只含自己的收藏、按 bookmarked_at
    DESC、取消收藏后消失、分页、未打标源文章也能收藏（meta 为 null）。
  - 未登录：401/403。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.news_source_meta import NewsSourceMeta
from app.models.user_article_state import UserArticleState
from app.services.news._model_loader import NewsArticle

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """Fresh in-memory SQLite with all tables (StaticPool for threads)."""
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
        Base.metadata.drop_all(engine)
        engine.dispose()


def _add_article(db, *, source: str, source_id: str, title: str = "t") -> NewsArticle:
    row = NewsArticle(
        source=source,
        source_id=source_id,
        url=f"https://example.com/{source}/{source_id}",
        url_hash=f"hash-{source}-{source_id}",
        title=title,
        summary="s",
        language="zh",
        market="cn_a",
        published_at=datetime.now(tz=UTC).replace(tzinfo=None),
    )
    db.add(row)
    db.commit()
    return row


class _FakeUser:
    """JWT 用户替身——id 可变，便于多用户隔离测试。"""

    def __init__(self, user_id: int = 1, username: str = "tester"):
        self.id = user_id
        self.username = username
        self.role = "user"


def _make_client(db, user: _FakeUser | None):
    """挂载 learning router 的 TestClient；user=None 表示未登录。

    未登录时不 override get_current_user——HTTPBearer 在没有
    Authorization 头时直接 403（FastAPI 默认），这就是 401/403 断言
    要覆盖的路径。
    """
    from fastapi import FastAPI

    from app.api.v1 import learning as learning_module

    def _override_db():
        try:
            yield db
        finally:
            pass

    test_app = FastAPI()
    test_app.include_router(learning_module.router, prefix="/api/v1/learning")
    test_app.dependency_overrides[learning_module.get_db] = _override_db
    if user is not None:
        test_app.dependency_overrides[learning_module.get_current_user] = (
            lambda: user
        )
    client = TestClient(test_app)
    return client, test_app


@pytest.fixture
def client(db):
    c, app = _make_client(db, _FakeUser(1))
    yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 模型 CRUD
# ---------------------------------------------------------------------------

class TestUserArticleStateCRUD:
    def test_insert_and_read(self, db):
        now = datetime.now(tz=UTC)
        db.add(UserArticleState(user_id=1, article_id=10, bookmarked_at=now))
        db.commit()
        row = db.get(UserArticleState, (1, 10))
        assert row is not None
        assert row.bookmarked_at is not None
        assert row.read_at is None

    def test_composite_pk_allows_same_article_different_users(self, db):
        db.add(UserArticleState(user_id=1, article_id=10))
        db.add(UserArticleState(user_id=2, article_id=10))
        db.commit()
        rows = db.execute(select(UserArticleState)).scalars().all()
        assert len(rows) == 2

    def test_nullable_timestamps_default_null(self, db):
        db.add(UserArticleState(user_id=1, article_id=10))
        db.commit()
        row = db.get(UserArticleState, (1, 10))
        assert row.bookmarked_at is None
        assert row.read_at is None


# ---------------------------------------------------------------------------
# 迁移脚本（revision 链 + 模型/迁移结构一致）
# ---------------------------------------------------------------------------

class TestMigration:
    @staticmethod
    def _load_migration_module():
        """按文件路径加载迁移脚本（alembic/versions 不是 Python 包）。"""
        import importlib.util
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[3]
            / "alembic"
            / "versions"
            / "x5y7z9a1b3c5_add_user_article_state.py"
        )
        spec = importlib.util.spec_from_file_location(
            "mig_user_article_state", path
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_revision_chain(self):
        """新迁移必须挂在 news_source_meta 迁移（w4x6y8z0a2b4）之后。"""
        mod = self._load_migration_module()
        assert mod.revision == "x5y7z9a1b3c5"
        assert mod.down_revision == "w4x6y8z0a2b4"

    def test_model_table_shape(self):
        """模型表结构断言——防模型与迁移脚本漂移。"""
        table = Base.metadata.tables["user_article_state"]
        cols = set(table.columns.keys())
        assert cols == {
            "user_id",
            "article_id",
            "bookmarked_at",
            "read_at",
            "created_at",
            "updated_at",
        }
        assert {c.name for c in table.primary_key.columns} == {
            "user_id",
            "article_id",
        }
        fks = {fk.target_fullname for fk in table.foreign_keys}
        assert fks == {"users.id", "news_article.id"}


# ---------------------------------------------------------------------------
# POST /learning/articles/{id}/bookmark
# ---------------------------------------------------------------------------

class TestBookmarkToggle:
    def test_bookmark_then_unbookmark(self, client, db):
        article = _add_article(db, source="deep_macro", source_id="m1")
        r1 = client.post(f"/api/v1/learning/articles/{article.id}/bookmark")
        assert r1.status_code == 200
        assert r1.json()["bookmarked"] is True
        assert r1.json()["bookmarked_at"] is not None

        r2 = client.post(f"/api/v1/learning/articles/{article.id}/bookmark")
        assert r2.json()["bookmarked"] is False
        assert r2.json()["bookmarked_at"] is None

        # 取消收藏不删行（已读状态得以保留）
        state = db.get(UserArticleState, (1, article.id))
        assert state is not None
        assert state.bookmarked_at is None

    def test_bookmark_keeps_read_state(self, client, db):
        article = _add_article(db, source="deep_macro", source_id="m1")
        client.post(f"/api/v1/learning/articles/{article.id}/read")
        client.post(f"/api/v1/learning/articles/{article.id}/bookmark")
        client.post(f"/api/v1/learning/articles/{article.id}/bookmark")  # 取消
        state = db.get(UserArticleState, (1, article.id))
        assert state.read_at is not None  # 已读没被取消收藏冲掉

    def test_bookmark_unknown_article_404(self, client):
        resp = client.post("/api/v1/learning/articles/999999/bookmark")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /learning/articles/{id}/read
# ---------------------------------------------------------------------------

class TestMarkRead:
    def test_mark_read_idempotent(self, client, db):
        article = _add_article(db, source="deep_macro", source_id="m1")
        r1 = client.post(f"/api/v1/learning/articles/{article.id}/read")
        assert r1.status_code == 200
        assert r1.json()["read"] is True
        first_read_at = r1.json()["read_at"]
        assert first_read_at is not None

        # 重复标记：200 且不刷新首次时间戳
        r2 = client.post(f"/api/v1/learning/articles/{article.id}/read")
        assert r2.status_code == 200
        assert r2.json()["read_at"] == first_read_at

    def test_read_unknown_article_404(self, client):
        resp = client.post("/api/v1/learning/articles/999999/read")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /learning/feed — bookmarked/read 布尔标注
# ---------------------------------------------------------------------------

class TestFeedStateFlags:
    def _seed(self, db):
        db.add(NewsSourceMeta(source="deep_macro", content_type="deep", topic="macro"))
        a1 = _add_article(db, source="deep_macro", source_id="m1", title="第一篇")
        a2 = _add_article(db, source="deep_macro", source_id="m2", title="第二篇")
        return a1, a2

    def test_feed_defaults_false(self, client, db):
        self._seed(db)
        data = client.get("/api/v1/learning/feed").json()
        assert data["total"] == 2
        for item in data["items"]:
            assert item["bookmarked"] is False
            assert item["read"] is False

    def test_feed_reflects_own_state(self, client, db):
        a1, a2 = self._seed(db)
        client.post(f"/api/v1/learning/articles/{a1.id}/bookmark")
        client.post(f"/api/v1/learning/articles/{a2.id}/read")
        items = {
            i["id"]: i for i in client.get("/api/v1/learning/feed").json()["items"]
        }
        assert items[a1.id]["bookmarked"] is True
        assert items[a1.id]["read"] is False
        assert items[a2.id]["bookmarked"] is False
        assert items[a2.id]["read"] is True

    def test_feed_does_not_leak_other_users_state(self, db):
        """用户 2 的收藏/已读绝不能出现在用户 1 的 feed 布尔里。"""
        a1, _ = self._seed(db)
        # 用户 2 收藏 + 已读 a1
        now = datetime.now(tz=UTC)
        db.add(
            UserArticleState(
                user_id=2, article_id=a1.id, bookmarked_at=now, read_at=now
            )
        )
        db.commit()
        client, app = _make_client(db, _FakeUser(1))
        try:
            items = client.get("/api/v1/learning/feed").json()["items"]
            mine = next(i for i in items if i["id"] == a1.id)
            assert mine["bookmarked"] is False
            assert mine["read"] is False
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /learning/bookmarks
# ---------------------------------------------------------------------------

class TestBookmarksList:
    def test_only_own_bookmarks(self, db):
        a1 = _add_article(db, source="s", source_id="1", title="我收藏的")
        a2 = _add_article(db, source="s", source_id="2", title="别人收藏的")
        now = datetime.now(tz=UTC)
        db.add(UserArticleState(user_id=1, article_id=a1.id, bookmarked_at=now))
        db.add(UserArticleState(user_id=2, article_id=a2.id, bookmarked_at=now))
        db.commit()
        client, app = _make_client(db, _FakeUser(1))
        try:
            data = client.get("/api/v1/learning/bookmarks").json()
            assert data["total"] == 1
            assert data["items"][0]["id"] == a1.id
            assert data["items"][0]["bookmarked"] is True
        finally:
            app.dependency_overrides.clear()

    def test_ordered_by_bookmarked_at_desc(self, client, db):
        a1 = _add_article(db, source="s", source_id="1", title="先收藏")
        a2 = _add_article(db, source="s", source_id="2", title="后收藏")
        now = datetime.now(tz=UTC)
        db.add(
            UserArticleState(
                user_id=1, article_id=a1.id, bookmarked_at=now - timedelta(hours=1)
            )
        )
        db.add(UserArticleState(user_id=1, article_id=a2.id, bookmarked_at=now))
        db.commit()
        data = client.get("/api/v1/learning/bookmarks").json()
        assert [i["id"] for i in data["items"]] == [a2.id, a1.id]

    def test_unbookmark_removes_from_list(self, client, db):
        article = _add_article(db, source="s", source_id="1")
        client.post(f"/api/v1/learning/articles/{article.id}/bookmark")
        assert client.get("/api/v1/learning/bookmarks").json()["total"] == 1
        client.post(f"/api/v1/learning/articles/{article.id}/bookmark")  # 取消
        assert client.get("/api/v1/learning/bookmarks").json()["total"] == 0

    def test_untagged_source_bookmarkable(self, client, db):
        """收藏不限于打标源——未打标源文章 meta 字段为 null。"""
        article = _add_article(db, source="flash_news", source_id="f1")
        client.post(f"/api/v1/learning/articles/{article.id}/bookmark")
        data = client.get("/api/v1/learning/bookmarks").json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["content_type"] is None
        assert item["topic"] is None
        assert item["bookmarked"] is True

    def test_pagination(self, client, db):
        now = datetime.now(tz=UTC)
        for i in range(3):
            a = _add_article(db, source="s", source_id=str(i))
            db.add(
                UserArticleState(
                    user_id=1,
                    article_id=a.id,
                    bookmarked_at=now + timedelta(minutes=i),
                )
            )
        db.commit()
        p1 = client.get(
            "/api/v1/learning/bookmarks", params={"page": 1, "page_size": 2}
        ).json()
        p2 = client.get(
            "/api/v1/learning/bookmarks", params={"page": 2, "page_size": 2}
        ).json()
        assert p1["total"] == 3
        assert p1["total_pages"] == 2
        assert len(p1["items"]) == 2
        assert len(p2["items"]) == 1

    def test_read_flag_in_bookmarks_list(self, client, db):
        article = _add_article(db, source="s", source_id="1")
        client.post(f"/api/v1/learning/articles/{article.id}/bookmark")
        client.post(f"/api/v1/learning/articles/{article.id}/read")
        item = client.get("/api/v1/learning/bookmarks").json()["items"][0]
        assert item["read"] is True


# ---------------------------------------------------------------------------
# 未登录
# ---------------------------------------------------------------------------

class TestUnauthenticated:
    def test_bookmark_requires_auth(self, db):
        client, app = _make_client(db, None)
        try:
            resp = client.post("/api/v1/learning/articles/1/bookmark")
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()

    def test_read_requires_auth(self, db):
        client, app = _make_client(db, None)
        try:
            resp = client.post("/api/v1/learning/articles/1/read")
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()

    def test_bookmarks_list_requires_auth(self, db):
        client, app = _make_client(db, None)
        try:
            resp = client.get("/api/v1/learning/bookmarks")
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()
