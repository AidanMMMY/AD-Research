"""Tests for the futures API endpoints.

Covers:
- /contracts: pagination, exchange/product filter, search.
- /daily: historical bars filtered by code.
- /dashboard: latest-day grouping by product.
- /leaderboard: gainers / losers / direction validation.
- /stats: diagnostics counts.

The DB dependency is overridden with an in-memory SQLite session backed
by a clean schema. The futures endpoints do not require auth so there's
no auth override needed; they sit behind the standard ``get_db`` dep.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps as api_deps
from app.core.database import Base
from app.main import app
from app.models.futures import FuturesContract, FuturesDailyBar


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    """In-memory SQLite session shared across threads via StaticPool."""
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
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(db_session):
    """TestClient with DB dependency overridden to the in-memory session."""

    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    with TestClient(app) as c:
        try:
            yield c
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_contract(
    db,
    code: str,
    name: str,
    exchange: str,
    product: str,
    *,
    is_main: bool = True,
):
    db.add(
        FuturesContract(
            code=code,
            name=name,
            exchange=exchange,
            product=product,
            is_main=is_main,
            source="akshare",
        )
    )


def _seed_bar(
    db,
    code: str,
    trade_date: date,
    *,
    settle="100.0000",
    pre_settle="99.0000",
    close="101.0000",
    open_="98.0000",
    high="102.0000",
    low="97.0000",
    volume=1000,
    open_interest=2000,
):
    db.add(
        FuturesDailyBar(
            code=code,
            trade_date=trade_date,
            open=Decimal(open_),
            high=Decimal(high),
            low=Decimal(low),
            close=Decimal(close),
            settle=Decimal(settle),
            pre_settle=Decimal(pre_settle),
            volume=volume,
            open_interest=open_interest,
            source="akshare",
        )
    )


# ---------------------------------------------------------------------------
# /futures/stats
# ---------------------------------------------------------------------------


def test_stats_returns_zeros_when_empty(client):
    resp = client.get("/api/v1/futures/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_contracts"] == 0
    assert body["total_bars"] == 0
    assert body["latest_trade_date"] is None


def test_stats_returns_counts(client, db_session):
    _seed_contract(db_session, "CU0", "沪铜主力", "SHFE", "金属")
    _seed_bar(
        db_session,
        "CU0",
        date(2026, 7, 1),
        settle="110.0000",
        pre_settle="100.0000",
    )
    db_session.commit()

    resp = client.get("/api/v1/futures/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_contracts"] == 1
    assert body["total_bars"] == 1
    assert body["latest_trade_date"] == "2026-07-01"


# ---------------------------------------------------------------------------
# /futures/contracts
# ---------------------------------------------------------------------------


def test_contracts_list_returns_seeded(client, db_session):
    _seed_contract(db_session, "CU0", "沪铜主力", "SHFE", "金属")
    _seed_contract(db_session, "M0", "豆粕主力", "DCE", "农产品")
    db_session.commit()

    resp = client.get("/api/v1/futures/contracts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    codes = {it["code"] for it in body["items"]}
    assert codes == {"CU0", "M0"}


def test_contracts_filter_by_exchange(client, db_session):
    _seed_contract(db_session, "CU0", "沪铜主力", "SHFE", "金属")
    _seed_contract(db_session, "M0", "豆粕主力", "DCE", "农产品")
    db_session.commit()

    resp = client.get("/api/v1/futures/contracts?exchange=SHFE")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["exchange"] == "SHFE"


def test_contracts_filter_by_product(client, db_session):
    _seed_contract(db_session, "CU0", "沪铜主力", "SHFE", "金属")
    _seed_contract(db_session, "M0", "豆粕主力", "DCE", "农产品")
    db_session.commit()

    resp = client.get("/api/v1/futures/contracts?product=%E5%86%9C%E4%BA%A7%E5%93%81")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["code"] == "M0"


def test_contracts_filter_by_search(client, db_session):
    _seed_contract(db_session, "CU0", "沪铜主力", "SHFE", "金属")
    _seed_contract(db_session, "M0", "豆粕主力", "DCE", "农产品")
    db_session.commit()

    resp = client.get("/api/v1/futures/contracts?search=%E9%93%9C")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["code"] == "CU0"


def test_contracts_pagination(client, db_session):
    for i in range(5):
        _seed_contract(
            db_session,
            f"X{i}0",
            f"合约{i}",
            "SHFE",
            "金属",
        )
    db_session.commit()

    resp = client.get("/api/v1/futures/contracts?page=1&page_size=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) == 2

    resp2 = client.get("/api/v1/futures/contracts?page=3&page_size=2")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert len(body2["items"]) == 1


# ---------------------------------------------------------------------------
# /futures/daily
# ---------------------------------------------------------------------------


def test_daily_returns_bars_in_ascending_order(client, db_session):
    _seed_contract(db_session, "CU0", "沪铜主力", "SHFE", "金属")
    _seed_bar(db_session, "CU0", date(2026, 7, 1))
    _seed_bar(
        db_session,
        "CU0",
        date(2026, 6, 30),
        settle="98.0000",
        pre_settle="97.0000",
    )
    db_session.commit()

    resp = client.get("/api/v1/futures/daily?code=CU0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["code"] == "CU0"
    # Ascending order by date
    dates = [it["trade_date"] for it in body["items"]]
    assert dates == ["2026-06-30", "2026-07-01"]


def test_daily_includes_settle_change_pct(client, db_session):
    _seed_contract(db_session, "CU0", "沪铜主力", "SHFE", "金属")
    _seed_bar(
        db_session,
        "CU0",
        date(2026, 7, 1),
        settle="110.0000",
        pre_settle="100.0000",
    )
    db_session.commit()

    resp = client.get("/api/v1/futures/daily?code=CU0")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    # (110-100)/100 * 100 = 10.0%
    assert abs(item["settle_change_pct"] - 10.0) < 1e-6


def test_daily_no_filter_returns_all(client, db_session):
    _seed_contract(db_session, "CU0", "沪铜主力", "SHFE", "金属")
    _seed_contract(db_session, "M0", "豆粕主力", "DCE", "农产品")
    _seed_bar(db_session, "CU0", date(2026, 7, 1))
    _seed_bar(db_session, "M0", date(2026, 7, 1))
    db_session.commit()

    resp = client.get("/api/v1/futures/daily")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["code"] is None


# ---------------------------------------------------------------------------
# /futures/dashboard
# ---------------------------------------------------------------------------


def test_dashboard_groups_by_product(client, db_session):
    _seed_contract(db_session, "CU0", "沪铜主力", "SHFE", "金属")
    _seed_contract(db_session, "AU0", "黄金主力", "SHFE", "金属")
    _seed_contract(db_session, "M0", "豆粕主力", "DCE", "农产品")
    _seed_bar(db_session, "CU0", date(2026, 7, 1), settle="110.0000", pre_settle="100.0000")
    _seed_bar(db_session, "AU0", date(2026, 7, 1), settle="200.0000", pre_settle="210.0000")
    _seed_bar(db_session, "M0", date(2026, 7, 1), settle="50.0000", pre_settle="49.0000")
    db_session.commit()

    resp = client.get("/api/v1/futures/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_contracts"] == 3
    assert body["trade_date"] == "2026-07-01"

    sections_by_product = {sec["product"]: sec for sec in body["sections"]}
    assert "金属" in sections_by_product
    assert sections_by_product["金属"]["count"] == 2
    # Best performer is the one with higher positive change_pct
    assert sections_by_product["金属"]["best_performer"]["code"] == "CU0"
    assert sections_by_product["金属"]["worst_performer"]["code"] == "AU0"


def test_dashboard_empty_when_no_data(client):
    resp = client.get("/api/v1/futures/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sections"] == []
    assert body["total_contracts"] == 0


# ---------------------------------------------------------------------------
# /futures/leaderboard
# ---------------------------------------------------------------------------


def test_leaderboard_gainers(client, db_session):
    _seed_contract(db_session, "CU0", "沪铜主力", "SHFE", "金属")
    _seed_contract(db_session, "M0", "豆粕主力", "DCE", "农产品")
    _seed_bar(db_session, "CU0", date(2026, 7, 1), settle="110.0000", pre_settle="100.0000")
    _seed_bar(db_session, "M0", date(2026, 7, 1), settle="50.0000", pre_settle="100.0000")
    db_session.commit()

    resp = client.get("/api/v1/futures/leaderboard?direction=gainers")
    assert resp.status_code == 200
    body = resp.json()
    assert body["direction"] == "gainers"
    assert len(body["items"]) == 2
    # First item is the gainer (CU0: +10%)
    assert body["items"][0]["code"] == "CU0"


def test_leaderboard_losers(client, db_session):
    _seed_contract(db_session, "CU0", "沪铜主力", "SHFE", "金属")
    _seed_contract(db_session, "M0", "豆粕主力", "DCE", "农产品")
    _seed_bar(db_session, "CU0", date(2026, 7, 1), settle="110.0000", pre_settle="100.0000")
    _seed_bar(db_session, "M0", date(2026, 7, 1), settle="50.0000", pre_settle="100.0000")
    db_session.commit()

    resp = client.get("/api/v1/futures/leaderboard?direction=losers")
    assert resp.status_code == 200
    body = resp.json()
    assert body["direction"] == "losers"
    # First item is the loser (M0: -50%)
    assert body["items"][0]["code"] == "M0"


def test_leaderboard_invalid_direction_returns_400(client):
    resp = client.get("/api/v1/futures/leaderboard?direction=sideways")
    assert resp.status_code == 400


def test_leaderboard_filters_by_exchange(client, db_session):
    _seed_contract(db_session, "CU0", "沪铜主力", "SHFE", "金属")
    _seed_contract(db_session, "M0", "豆粕主力", "DCE", "农产品")
    _seed_bar(db_session, "CU0", date(2026, 7, 1), settle="110.0000", pre_settle="100.0000")
    _seed_bar(db_session, "M0", date(2026, 7, 1), settle="50.0000", pre_settle="100.0000")
    db_session.commit()

    resp = client.get("/api/v1/futures/leaderboard?exchange=SHFE")
    assert resp.status_code == 200
    body = resp.json()
    assert body["exchange"] == "SHFE"
    assert len(body["items"]) == 1
    assert body["items"][0]["exchange"] == "SHFE"
