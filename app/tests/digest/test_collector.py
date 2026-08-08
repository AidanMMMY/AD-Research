"""Daily Digest 聚合层测试（2026-08-03，B2）。

Coverage:
  - 窗口边界计算：report_date 当日 06:30 Asia/Shanghai 收口，前一日
    06:30 起，半开区间。
  - 资讯包：窗口内 importance>=4 限量 40 + importance=3 补齐到 60；
    窗口外 / importance<3 不入选；event_category 分桶。
  - watchlist 包：主用户 UserFavorite ∪ PaperTradePosition 标的，
    逐标的行情/评分/窗口内关联新闻（≤5 条）。
  - 单包异常 → degraded 不中断，其余包正常采集。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# 注册全部 ORM 模型（create_all 需要）：app.models 覆盖大部分，
# favorite/notification/research 等未进 __init__ 的模块单独 import。
import app.models  # noqa: F401
from app.core.database import Base
from app.models import (  # noqa: F401
    etf_scan_log,
    etl,
    favorite,
    listing,
    notification,
    research,
    user_article_state,
)
from app.models.etf import ETFInfo, InstrumentDailyBar
from app.models.favorite import UserFavorite
from app.models.scoring import ETFScore
from app.models.trading import PaperTradeAccount, PaperTradePosition
from app.models.user import User
from app.services.digest.collector import (
    NEWS_TOTAL_LIMIT,
    SHANGHAI,
    DigestDataCollector,
)
from app.services.digest.context import DigestContext

# NewsArticle 须走 _model_loader（app/models/news.py 被同名包遮蔽）
from app.services.news._model_loader import NewsArticle, NewsArticleSymbol

REPORT_DATE = date(2026, 8, 3)
# 窗口 [2026-08-01 22:30 UTC, 2026-08-02 22:30 UTC)
WINDOW_START_UTC = datetime(2026, 8, 1, 22, 30)
WINDOW_END_UTC = datetime(2026, 8, 2, 22, 30)


@pytest.fixture
def digest_db():
    """SQLite 内存库（StaticPool），全表建 schema。"""
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


def _ctx() -> DigestContext:
    start, end = DigestDataCollector.compute_window(REPORT_DATE)
    return DigestContext(report_date=REPORT_DATE, window_start=start, window_end=end)


def _add_article(
    db,
    *,
    source_id: str,
    published_at: datetime,
    importance: int,
    event_category: str = "other",
    title: str | None = None,
) -> NewsArticle:
    row = NewsArticle(
        source="rss",
        source_id=source_id,
        url=f"https://example.com/{source_id}",
        url_hash=f"hash-{source_id}",
        title=title or f"标题-{source_id}",
        language="zh",
        market="US",
        published_at=published_at,
        importance=importance,
        event_category=event_category,
    )
    db.add(row)
    return row


# ---------------------------------------------------------------------------
# 窗口边界
# ---------------------------------------------------------------------------


def test_compute_window_boundaries():
    start, end = DigestDataCollector.compute_window(REPORT_DATE)
    assert end == datetime(2026, 8, 3, 6, 30, tzinfo=SHANGHAI)
    assert start == datetime(2026, 8, 2, 6, 30, tzinfo=SHANGHAI)
    assert end - start == timedelta(days=1)
    # tz-aware（Asia/Shanghai = UTC+8）
    assert end.utcoffset() == timedelta(hours=8)


# ---------------------------------------------------------------------------
# 资讯包
# ---------------------------------------------------------------------------


def test_news_window_and_importance_gate(digest_db):
    in_mid = WINDOW_START_UTC + timedelta(hours=6)
    _add_article(digest_db, source_id="h1", published_at=in_mid, importance=5,
                 event_category="central_bank")
    _add_article(digest_db, source_id="h2", published_at=in_mid, importance=4,
                 event_category="geopolitics")
    _add_article(digest_db, source_id="m1", published_at=in_mid, importance=3)
    # 窗口起点恰好 = start（半开区间含起点）
    _add_article(digest_db, source_id="edge", published_at=WINDOW_START_UTC,
                 importance=4, event_category="regulation")
    # 排除：窗口终点（半开不含）、窗口前、importance<3
    _add_article(digest_db, source_id="x-end", published_at=WINDOW_END_UTC, importance=5)
    _add_article(digest_db, source_id="x-before", published_at=WINDOW_START_UTC - timedelta(hours=1), importance=5)
    _add_article(digest_db, source_id="x-low", published_at=in_mid, importance=2)
    digest_db.commit()

    collector = DigestDataCollector(digest_db)
    ctx = _ctx()
    collector._collect_news(ctx)

    assert ctx.news["total"] == 4
    assert len(ctx.news["buckets"]["central_bank"]) == 1
    assert len(ctx.news["buckets"]["geopolitics"]) == 1
    assert len(ctx.news["buckets"]["regulation"]) == 1
    assert len(ctx.news["buckets"]["other"]) == 1  # m1 (importance=3 补齐)
    assert ctx.degraded == []
    assert "【央行】" in ctx.facts["news"]


def test_news_limits_high40_total60(digest_db):
    in_mid = WINDOW_START_UTC + timedelta(hours=6)
    for i in range(45):
        _add_article(digest_db, source_id=f"h{i}", published_at=in_mid, importance=5)
    for i in range(30):
        _add_article(digest_db, source_id=f"m{i}", published_at=in_mid, importance=3)
    digest_db.commit()

    collector = DigestDataCollector(digest_db)
    ctx = _ctx()
    collector._collect_news(ctx)

    assert ctx.news["total"] == NEWS_TOTAL_LIMIT == 60
    # importance>=4 上限 40，其余 20 条由 importance=3 补齐
    high = sum(
        1 for items in ctx.news["buckets"].values() for r in items if r["importance"] >= 4
    )
    mid = sum(
        1 for items in ctx.news["buckets"].values() for r in items if r["importance"] == 3
    )
    assert high == 40
    assert mid == 20


# ---------------------------------------------------------------------------
# watchlist 包
# ---------------------------------------------------------------------------


def _setup_watchlist(db):
    user = User(username="aidan", password_hash="x", role="user")
    db.add(user)
    db.flush()
    db.add(ETFInfo(code="510300.SH", name="沪深300ETF", market="A股"))
    db.add(ETFInfo(code="AAPL.US", name="Apple Inc.", name_zh="苹果", market="US"))
    db.add(
        InstrumentDailyBar(
            etf_code="510300.SH", trade_date=date(2026, 8, 1),
            close=4.123, change_pct=1.25,
        )
    )
    db.add(
        ETFScore(
            etf_code="510300.SH", trade_date=date(2026, 8, 1),
            template_id=1, composite_score=82.5, rank_overall=7,
        )
    )
    db.add(UserFavorite(id="aidan_510300.SH", username="aidan", etf_code="510300.SH"))
    account = PaperTradeAccount(
        user_id=user.id, name="默认账户", initial_balance=10000, cash=5000
    )
    db.add(account)
    db.flush()
    db.add(
        PaperTradePosition(
            account_id=account.id, instrument_code="AAPL.US",
            quantity=10, avg_cost=200.5, unrealized_pnl=150.0,
        )
    )
    # 窗口内关联新闻（510300.SH 2 条 / AAPL.US 1 条）+ 窗口外 1 条
    in_mid = WINDOW_START_UTC + timedelta(hours=3)
    for i in range(2):
        a = _add_article(db, source_id=f"w-sh-{i}", published_at=in_mid, importance=4)
        db.flush()
        db.add(NewsArticleSymbol(article_id=a.id, symbol="510300.SH"))
    a = _add_article(db, source_id="w-us-0", published_at=in_mid, importance=3)
    db.flush()
    db.add(NewsArticleSymbol(article_id=a.id, symbol="AAPL.US"))
    out = _add_article(db, source_id="w-out", published_at=WINDOW_END_UTC + timedelta(hours=2), importance=5)
    db.flush()
    db.add(NewsArticleSymbol(article_id=out.id, symbol="510300.SH"))
    db.commit()


def test_watchlist_favorite_union_position(digest_db):
    _setup_watchlist(digest_db)
    collector = DigestDataCollector(digest_db)
    ctx = _ctx()
    collector._collect_watchlist(ctx)

    wl = ctx.watchlist
    assert wl["primary_user"] == "aidan"
    assert wl["codes"] == ["510300.SH", "AAPL.US"]
    items = {it["code"]: it for it in wl["items"]}

    sh = items["510300.SH"]
    assert sh["is_favorite"] is True
    assert sh["position"] is None
    assert sh["bar"]["close"] == pytest.approx(4.123)
    assert sh["score"]["composite_score"] == pytest.approx(82.5)
    # 窗口内 2 条（窗口外那条被排除）
    assert len(sh["news"]) == 2

    us = items["AAPL.US"]
    assert us["is_favorite"] is False
    assert us["position"]["quantity"] == pytest.approx(10.0)
    assert len(us["news"]) == 1

    assert "苹果(AAPL.US" in ctx.facts["watchlist"]
    assert "持仓" in ctx.facts["watchlist"]


def test_watchlist_primary_user_missing(digest_db):
    """主用户不存在 → 空包 + facts 声明，不抛错。"""
    collector = DigestDataCollector(digest_db)
    ctx = _ctx()
    collector._collect_watchlist(ctx)
    assert ctx.watchlist["codes"] == []
    assert "不存在" in ctx.facts["watchlist"]


# ---------------------------------------------------------------------------
# 单包异常 → degraded 不中断
# ---------------------------------------------------------------------------


def test_single_package_failure_degraded(digest_db, monkeypatch):
    collector = DigestDataCollector(digest_db)

    def _boom(ctx):
        raise RuntimeError("macro exploded")

    monkeypatch.setattr(collector, "_collect_macro", _boom)
    ctx = collector.collect(REPORT_DATE)

    assert "macro" in ctx.degraded
    assert ctx.macro is None
    # 其余包照常采集（空库 → 空数据但不 degraded）
    assert ctx.news is not None and ctx.news["total"] == 0
    assert ctx.watchlist is not None
    assert "news" not in ctx.degraded
    meta = ctx.snapshot_meta()
    assert meta["degraded"] == ["macro"]
    assert meta["package_rows"]["macro"] is None
    assert meta["package_rows"]["news"] == 0


def test_collect_empty_db_all_packages(digest_db):
    """空库冒烟：8 包全部跑通，无 degraded。"""
    ctx = DigestDataCollector(digest_db).collect(REPORT_DATE)
    assert ctx.degraded == []
    assert set(ctx.facts) == {
        "macro", "sector", "scores", "fund_flow",
        "news", "watchlist", "sentiment", "sellside",
    }
