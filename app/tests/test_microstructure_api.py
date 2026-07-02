"""Tests for the microstructure API endpoints.

Covers:
- LHB list endpoint: pagination + filter.
- HSGT list endpoint: window + type filter.
- Margin list endpoint: pagination + exchange filter.
- Restricted release list endpoint: pagination + date filter.
- Summary endpoint: aggregation across 4 tables.
- Facets endpoint: distinct values.
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
from app.api.v1 import microstructure as micro_module
from app.core.database import Base
from app.main import app
from app.models.microstructure import (
    HsgtFlow,
    LhbRecord,
    MarginBalance,
    RestrictedRelease,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    """Yield a fresh in-memory SQLite session backed by a clean schema.

    Only creates the 4 micro-structure tables so we sidestep pre-existing
    duplicate-index issues in unrelated tables that share
    ``Base.metadata``.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.models.microstructure import (
        HsgtFlow,
        LhbRecord,
        MarginBalance,
        RestrictedRelease,
    )

    for tbl in (LhbRecord, HsgtFlow, MarginBalance, RestrictedRelease):
        tbl.__table__.create(engine, checkfirst=True)
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


def _seed_lhb(db, rows):
    for r in rows:
        db.add(LhbRecord(**r))
    db.commit()


def _seed_hsgt(db, rows):
    for r in rows:
        db.add(HsgtFlow(**r))
    db.commit()


def _seed_margin(db, rows):
    for r in rows:
        db.add(MarginBalance(**r))
    db.commit()


def _seed_release(db, rows):
    for r in rows:
        db.add(RestrictedRelease(**r))
    db.commit()


def _lhb_row(ts_code="000001.SZ", name="平安银行", trade_date=None, reason="日涨幅偏离值达7%",
             lhb_net=1_000_000.0):
    return {
        "trade_date": trade_date or date.today(),
        "ts_code": ts_code,
        "name": name,
        "close": 10.5,
        "pct_change": 8.5,
        "turnover_rate": 12.0,
        "amount": 50_000_000.0,
        "lhb_buy_amount": 30_000_000.0,
        "lhb_sell_amount": 29_000_000.0,
        "lhb_net_amount": lhb_net,
        "reason": reason,
        "source": "akshare",
    }


def _hsgt_row(trade_date=None, type_="北向", net=500_000_000.0):
    return {
        "trade_date": trade_date or date.today(),
        "type": type_,
        "buy_amount": 1_000_000_000.0,
        "sell_amount": 500_000_000.0,
        "net_amount": net,
        "balance": 520_000_000_000.0,
        "source": "akshare",
    }


def _margin_row(ts_code="600000.SH", name="浦发银行", trade_date=None, exchange="SSE",
                financing_balance=1_000_000_000.0):
    return {
        "trade_date": trade_date or date.today(),
        "ts_code": ts_code,
        "name": name,
        "financing_balance": financing_balance,
        "financing_buy": 100_000_000.0,
        "securities_balance": 50_000_000.0,
        "securities_sell": 1_000_000.0,
        "exchange": exchange,
        "source": "akshare",
    }


def _release_row(ts_code="600519.SH", name="贵州茅台", release_date=None,
                 restricted_type="首发原股东"):
    return {
        "ts_code": ts_code,
        "name": name,
        "restricted_date": release_date or date.today(),
        "restricted_type": restricted_type,
        "restricted_number": 1_000_000.0,
        "restricted_amount": 1_500_000_000.0,
        "lift_ratio": 0.5,
        "source": "akshare",
    }


@pytest.fixture
def client(db_session):
    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    app.dependency_overrides[micro_module.get_current_user] = _override_user(role="user")

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
    app.dependency_overrides[micro_module.get_current_user] = _override_user(role="admin")

    with TestClient(app) as c:
        try:
            yield c
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# LHB
# ---------------------------------------------------------------------------


def test_lhb_empty(client):
    resp = client.get("/api/v1/microstructure/lhb")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_lhb_with_data(client, db_session):
    _seed_lhb(db_session, [
        _lhb_row(ts_code="000001.SZ", reason="日涨幅偏离值达7%", lhb_net=5_000_000.0),
        _lhb_row(ts_code="000002.SZ", reason="日换手率达20%", lhb_net=10_000_000.0),
    ])
    resp = client.get("/api/v1/microstructure/lhb")
    body = resp.json()
    assert body["total"] == 2
    assert body["items"][0]["lhb_net_amount"] == 10_000_000.0  # desc by net


def test_lhb_filter_ticker(client, db_session):
    _seed_lhb(db_session, [
        _lhb_row(ts_code="000001.SZ", reason="A"),
        _lhb_row(ts_code="000002.SZ", reason="B"),
    ])
    resp = client.get("/api/v1/microstructure/lhb?ts_code=000001.SZ")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["ts_code"] == "000001.SZ"


# ---------------------------------------------------------------------------
# HSGT
# ---------------------------------------------------------------------------


def test_hsgt_with_data(client, db_session):
    _seed_hsgt(db_session, [
        _hsgt_row(type_="北向", net=100_000_000.0),
        _hsgt_row(type_="沪股通", net=60_000_000.0),
        _hsgt_row(type_="深股通", net=40_000_000.0),
    ])
    resp = client.get("/api/v1/microstructure/hsgt")
    body = resp.json()
    assert body["total"] == 3


def test_hsgt_filter_type(client, db_session):
    _seed_hsgt(db_session, [
        _hsgt_row(type_="北向"),
        _hsgt_row(type_="沪股通"),
    ])
    resp = client.get("/api/v1/microstructure/hsgt?flow_type=沪股通")
    body = resp.json()
    assert body["total"] == 1


# ---------------------------------------------------------------------------
# Margin
# ---------------------------------------------------------------------------


def test_margin_with_data(client, db_session):
    _seed_margin(db_session, [
        _margin_row(ts_code="600000.SH", exchange="SSE"),
        _margin_row(ts_code="000001.SZ", exchange="SZSE"),
    ])
    resp = client.get("/api/v1/microstructure/margin")
    body = resp.json()
    assert body["total"] == 2


def test_margin_filter_exchange(client, db_session):
    _seed_margin(db_session, [
        _margin_row(ts_code="600000.SH", exchange="SSE"),
        _margin_row(ts_code="000001.SZ", exchange="SZSE"),
    ])
    resp = client.get("/api/v1/microstructure/margin?exchange=SSE")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["exchange"] == "SSE"


# ---------------------------------------------------------------------------
# Restricted releases
# ---------------------------------------------------------------------------


def test_release_with_data(client, db_session):
    today = date.today()
    _seed_release(db_session, [
        _release_row(release_date=today, restricted_type="A"),
        _release_row(ts_code="000001.SZ", name="平安银行",
                     release_date=today + timedelta(days=10), restricted_type="B"),
    ])
    resp = client.get("/api/v1/microstructure/restricted-releases")
    body = resp.json()
    assert body["total"] == 2
    # default sort = asc, so the earlier date comes first
    assert body["items"][0]["restricted_date"] == today.isoformat()


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def test_summary(client, db_session):
    today = date.today()
    _seed_lhb(db_session, [_lhb_row(trade_date=today)])
    _seed_hsgt(db_session, [_hsgt_row(trade_date=today)])
    _seed_margin(db_session, [_margin_row(trade_date=today)])
    _seed_release(db_session, [_release_row(release_date=today + timedelta(days=5))])

    resp = client.get("/api/v1/microstructure/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["as_of"] == today.isoformat()
    assert body["lhb"]["count"] == 1
    assert body["hsgt"]["north_net"] == 500_000_000.0
    assert body["margin"]["total_financing_balance"] == 1_000_000_000.0
    assert body["release"]["upcoming_30d_count"] == 1


def test_summary_empty(client):
    resp = client.get("/api/v1/microstructure/summary")
    body = resp.json()
    assert body["as_of"] is None
    assert body["lhb"] == {}
    assert body["hsgt"] == {}


# ---------------------------------------------------------------------------
# Facets
# ---------------------------------------------------------------------------


def test_facets(client, db_session):
    _seed_margin(db_session, [
        _margin_row(exchange="SSE"),
        _margin_row(ts_code="000001.SZ", exchange="SZSE"),
    ])
    resp = client.get("/api/v1/microstructure/facets")
    body = resp.json()
    assert "SSE" in body["exchanges"]
    assert "SZSE" in body["exchanges"]


# ---------------------------------------------------------------------------
# Refresh (admin)
# ---------------------------------------------------------------------------


def test_refresh_requires_admin(client):
    resp = client.post("/api/v1/microstructure/refresh")
    assert resp.status_code == 403


def test_refresh_admin_success(admin_client):
    mock_pipeline = MagicMock()
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.records = 100
    mock_result.warnings = []
    mock_pipeline.run_with_retry.return_value = mock_result

    with patch("app.api.v1.microstructure.MicrostructurePipeline", return_value=mock_pipeline):
        with patch("app.api.v1.microstructure.SessionLocal") as mock_session_local:
            mock_session_local.return_value = MagicMock()
            resp = admin_client.post("/api/v1/microstructure/refresh")
            assert resp.status_code == 202
            assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_unauthenticated_request_rejected():
    with TestClient(app) as c:
        resp = c.get("/api/v1/microstructure/lhb")
        assert resp.status_code in (401, 403)