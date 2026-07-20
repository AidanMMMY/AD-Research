"""End-to-end test for the sector-rotation API surface.

Verifies that the router responds at BOTH the historical /analysis/sector-rotation
prefix and the documented /sector-rotation prefix. Both routes must return
HTTP 200 with a payload that matches the SectorRotationResponse schema.

The sector rotation endpoint was redesigned 2026-07-08 to expose GICS
industry sectors rather than ETF fund categories, and to include both
individual stocks and ETFs in the aggregation. This test seeds both
types and asserts the new contract.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user, get_db, get_sector_rotation_service
from app.api.v1 import sector_rotation as sector_rotation_module
from app.core.database import Base
from app.models.etf import ETFIndicator, ETFInfo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sr_engine():
    """In-memory SQLite with StaticPool so all connections share one DB."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def sr_session(sr_engine):
    """Yield a SQLAlchemy session bound to the StaticPool engine."""
    SessionLocal = sessionmaker(bind=sr_engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def sector_rotation_client(sr_session):
    """Build a TestClient with the sector-rotation router mounted twice."""
    test_app = FastAPI()
    test_app.include_router(
        sector_rotation_module.router, prefix="/api/v1/analysis"
    )
    test_app.include_router(
        sector_rotation_module.router, prefix="/api/v1"
    )

    def _override_db():
        try:
            yield sr_session
        finally:
            pass

    def _override_service():
        from app.services.sector_rotation_service import SectorRotationService
        return SectorRotationService(sr_session)

    def _fake_user():
        from types import SimpleNamespace

        return SimpleNamespace(id=1, username="tester", role="user", is_active=True)

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_sector_rotation_service] = _override_service
    test_app.dependency_overrides[get_current_user] = _fake_user

    with TestClient(test_app) as client:
        yield client
    test_app.dependency_overrides.clear()


@pytest.fixture
def seeded_sector_universe(sr_session):
    """Insert 3 GICS sectors x (1 STOCK + 1 ETF) with 2 trade-dates of indicators.

    Stocks have their GICS ``sector`` populated (the production pipeline
    writes this). ETFs do not — they're resolved via the
    ``ETF_SECTOR_HINTS`` heuristic from ``sub_category``.

    Two dates are required so the rotation-signal detector has a previous
    period to compare against.
    """
    import datetime as dt

    # Tuple: (code, name, market, instrument_type, sector, sw_l1, sub_category, category, r1m, r3m, shp, vol, rsi)
    profiles = [
        # Information Technology (GICS) / 电子 (SW) — 1 stock + 1 ETF
        ("600000.SH", "Stock IT",   "A股", "STOCK", "Information Technology", "电子", None, None,
         10.0, 25.0, 2.0, 25.0, 75.0),
        ("512760.SH", "Tech ETF",   "A股", "ETF",   None, None, "科技ETF", "股票型",
         8.0, 20.0, 1.8, 22.0, 70.0),
        # Health Care (GICS) / 医药生物 (SW)
        ("600519.SH", "Stock HC",   "A股", "STOCK", "Health Care", "医药生物", None, None,
         6.0, 14.0, 1.4, 18.0, 60.0),
        ("510300.SH", "Med ETF",    "A股", "ETF",   None, None, "医药ETF", "股票型",
         4.0, 10.0, 1.2, 16.0, 55.0),
        # Financials (GICS) / 银行 (SW)
        ("601318.SH", "Stock FIN",  "A股", "STOCK", "Financials", "银行", None, None,
         1.0, 3.0, 0.8, 10.0, 45.0),
        ("510500.SH", "Bank ETF",   "A股", "ETF",   None, None, "银行ETF", "股票型",
         0.5, 2.0, 0.7, 8.0, 42.0),
        # Bond ETF — out of scope (category=债券型), must NOT show up in sectors
        ("511260.SH", "Bond ETF",   "A股", "ETF",   None, None, None, "债券型",
         0.3, 0.5, 0.6, 2.0, 50.0),
    ]

    dates = [dt.date(2024, 6, 23), dt.date(2024, 6, 30)]
    for (
        code, name, market, itype, sector, sw_l1, sub_cat, category,
        r1m, r3m, shp, vol, rsi,
    ) in profiles:
        sr_session.add(
            ETFInfo(
                code=code,
                name=name,
                market=market,
                instrument_type=itype,
                category=category,
                sub_category=sub_cat,
                sector=sector,
                sw_l1=sw_l1,
                status="active",
            )
        )
        for td in dates:
            sr_session.add(
                ETFIndicator(
                    etf_code=code,
                    trade_date=td,
                    return_1w=Decimal("1.0"),
                    return_1m=Decimal(str(r1m)),
                    return_3m=Decimal(str(r3m)),                    return_1y=Decimal("20.0"),
                    sharpe_1y=Decimal(str(shp)),
                    volatility_20d=Decimal(str(vol)),
                    max_drawdown_1y=Decimal("-10.0"),
                    rsi14=Decimal(str(rsi)),
                    ma5=Decimal("100.0"),
                    ma20=Decimal("100.0"),
                    amount=Decimal("1000000.0"),
                )
            )
    sr_session.commit()
    return {"trade_date": dates[-1], "codes": [p[0] for p in profiles]}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prefix",
    ["/api/v1/analysis/sector-rotation", "/api/v1/sector-rotation"],
    ids=["legacy-analysis-prefix", "documented-root-prefix"],
)
def test_sector_rotation_analyze_returns_200_on_both_paths(
    sector_rotation_client, seeded_sector_universe, prefix
):
    """Both /analysis/sector-rotation and /sector-rotation must respond 200."""
    resp = sector_rotation_client.get(prefix, params={"window_weeks": 4})
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    assert payload["trade_date"] == "2024-06-30"
    assert isinstance(payload["sectors"], list)
    assert "market_avg" in payload
    assert isinstance(payload["rotation_signals"], list)

    # Scope block must explicitly state A股 + GICS
    scope = payload["scope"]
    assert scope["market"] == "A股"
    assert scope["classification"] == "GICS"
    assert set(scope["instrument_types"]) == {"ETF", "STOCK"}

    # 3 GICS sectors seeded (Information Technology, Health Care, Financials).
    # The bond ETF is correctly excluded (no sector resolved).
    sector_names = {row["sector"] for row in payload["sectors"]}
    assert sector_names == {"Information Technology", "Health Care", "Financials"}

    # Each sector row has the documented fields (post-redesign 2026-07-08)
    expected_fields = {
        "sector", "count", "stock_count", "etf_count",
        "return_1w", "return_1m", "return_3m", "return_6m", "return_1y",
        "sharpe_1y", "volatility_20d", "rsi14", "amount_total",        "relative_strength_1w", "relative_strength_1m", "relative_strength_3m",
        "momentum_rank",
    }
    for row in payload["sectors"]:
        assert expected_fields.issubset(row.keys()), row
        # Stock + ETF counts must add up to total
        assert row["stock_count"] + row["etf_count"] == row["count"]

    # Momentum ranks are a contiguous 1..N sequence
    ranks = sorted(s["momentum_rank"] for s in payload["sectors"])
    assert ranks == list(range(1, len(payload["sectors"]) + 1))

    # Top sector by 1m return should be Information Technology
    top = payload["sectors"][0]
    assert top["sector"] == "Information Technology"
    assert top["momentum_rank"] == 1


@pytest.mark.parametrize(
    "prefix",
    ["/api/v1/analysis/sector-rotation", "/api/v1/sector-rotation"],
    ids=["legacy-analysis-prefix", "documented-root-prefix"],
)
def test_sector_rotation_sectors_returns_industry_sectors(
    sector_rotation_client, seeded_sector_universe, prefix
):
    """The /sectors sub-endpoint must list each unique GICS sector with counts."""
    resp = sector_rotation_client.get(f"{prefix}/sectors")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert "items" in payload
    sectors = {item["sector"] for item in payload["items"]}
    # Same as /analyze — bond ETF must be excluded
    assert sectors == {"Information Technology", "Health Care", "Financials"}
    for item in payload["items"]:
        assert item["count"] >= 1
        assert item["stock_count"] + item["etf_count"] == item["count"]


def test_sector_rotation_excludes_bond_etf(sector_rotation_client, seeded_sector_universe):
    """Bond ETFs (no equity sector) must not appear in either endpoint."""
    analyze = sector_rotation_client.get("/api/v1/sector-rotation").json()
    sectors = {row["sector"] for row in analyze["sectors"]}
    # Bond ETF would resolve to "Broad Market" — but its category is 债券型
    # and we exclude non-equity ETFs entirely. Confirm no Broad Market row.
    assert "Broad Market" not in sectors

    list_resp = sector_rotation_client.get("/api/v1/sector-rotation/sectors").json()
    list_sectors = {item["sector"] for item in list_resp["items"]}
    assert "Broad Market" not in list_sectors


def test_sector_rotation_query_param_validation(sector_rotation_client):
    """Out-of-range window_weeks should be rejected with 422."""
    resp = sector_rotation_client.get(
        "/api/v1/sector-rotation", params={"window_weeks": 999}
    )
    assert resp.status_code == 422


def test_sector_rotation_sw_classification_returns_sw_industries(
    sector_rotation_client, seeded_sector_universe
):
    """classification=SW must bucket by 申万一级行业, not GICS."""
    resp = sector_rotation_client.get(
        "/api/v1/sector-rotation", params={"classification": "SW"}
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    # Scope now reports SW.
    assert payload["scope"]["classification"] == "SW"

    # STOCKs bucket by etf_info.sw_l1; ETFs by 申万 keyword hints. The seed
    # pairs each SW industry with one stock + one themed ETF.
    sector_names = {row["sector"] for row in payload["sectors"]}
    assert sector_names == {"电子", "医药生物", "银行"}

    # No GICS names should leak into the SW view.
    assert "Information Technology" not in sector_names
    assert "Broad Market" not in sector_names

    for row in payload["sectors"]:
        assert row["stock_count"] + row["etf_count"] == row["count"]
        # Each SW bucket has exactly its stock + themed ETF.
        assert row["stock_count"] == 1
        assert row["etf_count"] == 1


def test_sector_rotation_default_classification_is_gics(
    sector_rotation_client, seeded_sector_universe
):
    """Omitting ``classification`` must keep the GICS default."""
    resp = sector_rotation_client.get("/api/v1/sector-rotation")
    assert resp.status_code == 200, resp.text
    assert resp.json()["scope"]["classification"] == "GICS"


def test_sector_list_sw_classification(
    sector_rotation_client, seeded_sector_universe
):
    """The /sectors sub-endpoint must honour classification=SW."""
    resp = sector_rotation_client.get(
        "/api/v1/sector-rotation/sectors", params={"classification": "SW"}
    )
    assert resp.status_code == 200, resp.text
    sectors = {item["sector"] for item in resp.json()["items"]}
    assert sectors == {"电子", "医药生物", "银行"}

