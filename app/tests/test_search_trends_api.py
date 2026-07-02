"""Tests for the search-trends API endpoints.

Covers:
- List endpoint: pagination + filters (source, region, category, keyword, date range).
- Dashboard endpoint: aggregate latest-day summary.
- Compare endpoint: keyword time-series across sources.
- Refresh endpoint: admin-only.
- Auth: every endpoint requires a logged-in user.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps as api_deps
from app.api.v1 import search_trends as st_module
from app.core.database import Base
from app.main import app
from app.models.search_trends import SearchTrend


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    """Yield a fresh in-memory SQLite session backed by a clean schema.

    Only creates the ``search_trends`` table so we sidestep pre-existing
    duplicate-index issues in unrelated tables that share
    ``Base.metadata``.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.models.search_trends import SearchTrend

    SearchTrend.__table__.create(engine, checkfirst=True)
    Session_ = sessionmaker(bind=engine)
    session = Session_()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _override_user(role: str = "user"):
    from app.schemas.auth import UserResponse

    def _dep():
        return UserResponse(id=1, username="tester", role=role)

    return _dep


def _seed(db, rows):
    for r in rows:
        db.add(SearchTrend(**r))
    db.commit()


def _row(keyword="上证指数", source="baidu", region="CN",
         value=1000, trade_date=None, category="indices"):
    return {
        "keyword": keyword,
        "region": region,
        "source": source,
        "trade_date": trade_date or date.today(),
        "value": value,
        "is_partial": False,
        "proxy_quality": "high",
        "category": category,
    }


@pytest.fixture
def client(db_session):
    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    app.dependency_overrides[st_module.get_current_user] = _override_user(role="user")

    with TestClient(app) as c:
        try:
            yield c
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def admin_client(db_session):
    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    app.dependency_overrides[st_module.get_current_user] = _override_user(role="admin")

    with TestClient(app) as c:
        try:
            yield c
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_list_empty(client):
    resp = client.get("/api/v1/search-trends")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0


def test_list_with_data(client, db_session):
    today = date.today()
    _seed(db_session, [
        _row(keyword="上证指数", source="baidu", value=1000, trade_date=today),
        _row(keyword="宁德时代", source="baidu", value=2000, trade_date=today),
        _row(keyword="宁德时代", source="google", region="GLOBAL", value=500, trade_date=today),
    ])
    resp = client.get("/api/v1/search-trends")
    body = resp.json()
    assert body["total"] == 3


def test_list_filter_source(client, db_session):
    _seed(db_session, [
        _row(source="baidu"),
        _row(keyword="A", source="google", region="GLOBAL"),
    ])
    resp = client.get("/api/v1/search-trends?source=baidu")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["source"] == "baidu"


def test_list_filter_keyword(client, db_session):
    _seed(db_session, [
        _row(keyword="上证指数"),
        _row(keyword="宁德时代"),
    ])
    resp = client.get("/api/v1/search-trends?keyword=宁德时代")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["keyword"] == "宁德时代"


def test_list_filter_category(client, db_session):
    _seed(db_session, [
        _row(keyword="A", category="indices"),
        _row(keyword="B", category="macro"),
    ])
    resp = client.get("/api/v1/search-trends?category=macro")
    body = resp.json()
    assert body["total"] == 1


def test_list_date_range(client, db_session):
    _seed(db_session, [
        _row(keyword="A", trade_date=date(2025, 1, 1)),
        _row(keyword="B", trade_date=date(2026, 6, 1)),
    ])
    resp = client.get("/api/v1/search-trends?start_date=2026-01-01&end_date=2026-12-31")
    body = resp.json()
    assert body["total"] == 1


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def test_dashboard_with_data(client, db_session):
    today = date.today()
    _seed(db_session, [
        _row(keyword="A", source="baidu", value=5000, trade_date=today),
        _row(keyword="B", source="baidu", value=3000, trade_date=today),
        _row(keyword="C", source="google", region="GLOBAL", value=1000, trade_date=today),
    ])
    resp = client.get("/api/v1/search-trends/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["as_of"] == today.isoformat()
    assert body["baidu"]["count"] == 2
    assert body["google"]["count"] == 1
    assert body["baidu"]["top_keywords"][0]["value"] == 5000


def test_dashboard_empty(client):
    resp = client.get("/api/v1/search-trends/dashboard")
    body = resp.json()
    assert body["as_of"] is None
    assert body["baidu"] == {}
    assert body["google"] == {}


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------


def test_compare_keyword(client, db_session):
    today = date.today()
    yesterday = today - timedelta(days=1)
    _seed(db_session, [
        _row(keyword="上证指数", source="baidu", value=1000, trade_date=yesterday),
        _row(keyword="上证指数", source="baidu", value=1200, trade_date=today),
        _row(keyword="上证指数", source="google", region="GLOBAL", value=80, trade_date=today),
    ])
    resp = client.get("/api/v1/search-trends/compare?keyword=%E4%B8%8A%E8%AF%81%E6%8C%87%E6%95%B0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["keyword"] == "上证指数"
    assert len(body["series"]) == 3


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------


def test_refresh_requires_admin(client):
    resp = client.post("/api/v1/search-trends/refresh")
    assert resp.status_code == 403


def test_refresh_admin_success(admin_client):
    mock_pipeline = MagicMock()
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.records = 8
    mock_result.warnings = []
    mock_pipeline.run_with_retry.return_value = mock_result

    with patch("app.api.v1.search_trends.SearchTrendsPipeline", return_value=mock_pipeline):
        with patch("app.api.v1.search_trends.SessionLocal") as mock_session_local:
            mock_session_local.return_value = MagicMock()
            resp = admin_client.post("/api/v1/search-trends/refresh")
            assert resp.status_code == 202
            assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_unauthenticated_request_rejected():
    with TestClient(app) as c:
        resp = c.get("/api/v1/search-trends")
        assert resp.status_code in (401, 403)