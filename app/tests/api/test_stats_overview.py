"""stats /overview{,/{metric}} 回归测试（2026-08-05）。

事故：per-metric 端点改为单条 COUNT 时误用 ``ETFInfo.id``——该表主键
是 ``code``（String），没有 id 列 → /stats/overview/etf-count 500。
测试真空（该端点此前零覆盖）。此处补齐：4 个 metric 端点 + 打包
/overview 全部打一遍真实 SQLite，并验证 60s 缓存语义。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  注册全部 ORM（create_all 需要）
from app.api import deps as api_deps
from app.core.database import Base
from app.main import app
from app.models.etf import ETFInfo
from app.models.scoring import ETFScore, ScoreTemplate

BASE = "/api/v1/stats"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine)
    session = Session_()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session, monkeypatch):
    """TestClient + 绕过鉴权 + 每次测试清空 overview 缓存。"""
    from app.api.v1 import stats as stats_module

    monkeypatch.setattr(stats_module, "_overview_cache", {})

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    fake_user = type("U", (), {"id": 1, "username": "t", "role": "admin"})()
    app.dependency_overrides[api_deps.get_db] = override_get_db
    app.dependency_overrides[api_deps.get_current_user] = lambda: fake_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def seeded(db_session):
    db_session.add(
        ETFInfo(code="510300.SH", name="沪深300ETF", market="A股", category="宽基")
    )
    db_session.add(ScoreTemplate(id=1, name="t1", weights={}))
    db_session.add(
        ETFScore(
            id=1, etf_code="510300.SH", trade_date=__import__("datetime").date(2026, 8, 4),
            template_id=1, composite_score=80.0,
        )
    )
    db_session.commit()
    return db_session


class TestOverviewEndpoints:
    def test_bundled_overview(self, client, seeded):
        resp = client.get(f"{BASE}/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["etf_count"] == 1
        assert data["template_count"] == 1
        assert data["score_count"] == 1
        assert data["category_count"] == 1

    @pytest.mark.parametrize(
        "metric,expected",
        [
            ("etf-count", 1),
            ("score-count", 1),
            ("category-count", 1),
            ("template-count", 1),
        ],
    )
    def test_per_metric(self, client, seeded, metric, expected):
        resp = client.get(f"{BASE}/overview/{metric}")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"value": expected, "metric": metric}

    def test_unknown_metric_404(self, client, seeded):
        resp = client.get(f"{BASE}/overview/nope")
        assert resp.status_code == 404

    def test_cache_collapses_repeat_calls(self, client, seeded, monkeypatch):
        from app.api.v1 import stats as stats_module

        calls = {"n": 0}
        original = stats_module._count_etf

        def counting(db):
            calls["n"] += 1
            return original(db)

        monkeypatch.setitem(stats_module._METRIC_QUERIES, "etf-count", counting)
        assert client.get(f"{BASE}/overview/etf-count").status_code == 200
        assert client.get(f"{BASE}/overview/etf-count").status_code == 200
        assert calls["n"] == 1  # 第二次命中缓存，不再查库
