"""End-to-end test for the sector-rotation API surface.

Verifies that the router responds at BOTH the historical /analysis/sector-rotation
prefix and the documented /sector-rotation prefix. Both routes must return
HTTP 200 with a payload that matches the SectorRotationResponse schema.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_sector_rotation_service
from app.api.v1 import sector_rotation as sector_rotation_module
from app.core.database import Base
from app.models.etf import ETFIndicator, ETFInfo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sr_engine():
    """In-memory SQLite with StaticPool so all connections share one DB.

    StaticPool is required because :memory: SQLite is per-connection —
    without it, the TestClient's request handler opens a different
    connection and sees an empty database.
    """
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
    """Build a TestClient with the sector-rotation router mounted twice.

    Mounts the router under:
      - /api/v1/analysis   (legacy /analysis/sector-rotation)
      - /api/v1            (documented /sector-rotation)
    so a single test can exercise both surfaces.
    """
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

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_sector_rotation_service] = _override_service

    with TestClient(test_app) as client:
        yield client
    test_app.dependency_overrides.clear()


@pytest.fixture
def seeded_sector_universe(sr_session):
    """Insert 3 categories x 2 ETFs with 2 trade-dates of indicators.

    Two dates are required so the rotation-signal detector has a previous
    period to compare against.
    """
    profiles = [
        # (code, name, category, return_1m, return_3m, sharpe_1y, vol20, rsi)
        ("510300.SH", "CSI 300 ETF",   "股票型",  8.0,  18.0, 2.0, 15.0, 70.0),
        ("510500.SH", "CSI 500 ETF",   "股票型",  5.0,  12.0, 1.4, 18.0, 60.0),
        ("511010.SH", "Treasury Bond", "债券型",  0.5,   2.0, 0.9,  5.0, 45.0),
        ("511260.SH", "Corp Bond",     "债券型",  0.8,   2.5, 1.0,  6.0, 48.0),
        ("512760.SH", "Tech ETF",      "科技型", 10.0,  25.0, 1.8, 25.0, 75.0),
        ("513500.SH", "S&P 500 ETF",   "科技型",  3.0,   8.0, 1.6, 12.0, 55.0),
    ]
    import datetime as dt
    dates = [dt.date(2024, 6, 23), dt.date(2024, 6, 30)]
    for code, name, category, r1m, r3m, shp, vol, rsi in profiles:
        sr_session.add(
            ETFInfo(
                code=code, name=name, market="E2E_SR", category=category, status="active",
            )
        )
        for td in dates:
            sr_session.add(
                ETFIndicator(
                    etf_code=code,
                    trade_date=td,
                    return_1m=Decimal(str(r1m)),
                    return_3m=Decimal(str(r3m)),
                    return_1y=Decimal("20.0"),
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

    assert "trade_date" in payload
    assert payload["trade_date"] == "2024-06-30"
    assert "sectors" in payload and isinstance(payload["sectors"], list)
    assert "market_avg" in payload
    assert "rotation_signals" in payload and isinstance(payload["rotation_signals"], list)

    # 3 distinct categories seeded -> 3 sector rows
    assert len(payload["sectors"]) == 3

    # Every sector row has the documented fields
    expected_fields = {
        "category", "count", "return_1m", "return_3m", "sharpe_1y",
        "volatility_20d", "rsi14", "relative_strength_1m",
        "relative_strength_3m", "momentum_rank",
    }
    for row in payload["sectors"]:
        assert expected_fields.issubset(row.keys()), row

    # Momentum ranks are a contiguous 1..N sequence
    ranks = sorted(s["momentum_rank"] for s in payload["sectors"])
    assert ranks == [1, 2, 3]


@pytest.mark.parametrize(
    "prefix",
    ["/api/v1/analysis/sector-rotation", "/api/v1/sector-rotation"],
    ids=["legacy-analysis-prefix", "documented-root-prefix"],
)
def test_sector_rotation_sectors_returns_categories(
    sector_rotation_client, seeded_sector_universe, prefix
):
    """The /sectors sub-endpoint must list each unique ETF category with a count."""
    resp = sector_rotation_client.get(f"{prefix}/sectors")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert "items" in payload
    categories = {item["category"] for item in payload["items"]}
    assert categories == {"股票型", "债券型", "科技型"}
    for item in payload["items"]:
        assert item["count"] >= 1


def test_sector_rotation_query_param_validation(sector_rotation_client):
    """Out-of-range window_weeks should be rejected with 422."""
    resp = sector_rotation_client.get(
        "/api/v1/sector-rotation", params={"window_weeks": 999}
    )
    assert resp.status_code == 422
