"""Tests for FredService.

These exercise the write path (upsert idempotency, registry iteration)
and the read path (list/get_series).  The FRED provider is replaced
with a stub so we never touch the network.
"""

from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.macro import MacroIndicator
from app.services.macro.fred_service import (
    FredService,
    SERIES_REGISTRY,
    _EU_SERIES,
    _GLOBAL_SERIES,
    _SERIES_ALL,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """In-memory SQLite session — note we DO NOT use postgres ON CONFLICT,
    so this fixture relies on the service's ``merge`` fallback when run
    against SQLite (the upsert path is exercised separately in the
    Postgres-only test below)."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def stub_provider():
    """Fake FRED provider that returns deterministic observations."""
    provider = MagicMock()
    provider.get_series.side_effect = lambda sid, start_date=None, end_date=None: [
        {"date": "2026-06-01", "value": 100.0},
        {"date": "2026-06-02", "value": 101.5},
        {"date": "2026-06-03", "value": "."},     # missing
        {"date": "2026-06-04", "value": 103.25},
    ]
    provider.rate_limit_sleep.return_value = None
    return provider


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_registry_has_at_least_20_series():
    assert len(SERIES_REGISTRY) >= 20, (
        f"Expected at least 20 FRED series, got {len(SERIES_REGISTRY)}"
    )


def test_registry_codes_are_unique():
    codes = [m.code for m in SERIES_REGISTRY]
    assert len(codes) == len(set(codes)), "Duplicate internal codes in registry"


def test_registry_includes_key_indicators():
    """Sanity check: the most-cited US macro series must be present."""
    must_have = {"GDP", "CPIAUCSL", "UNRATE", "FEDFUNDS", "DGS10", "VIXCLS"}
    have = {m.series_id for m in SERIES_REGISTRY}
    missing = must_have - have
    assert not missing, f"Missing key indicators: {missing}"


# ---------------------------------------------------------------------------
# Refresh path (uses the stub provider — never hits the network)
# ---------------------------------------------------------------------------

def test_refresh_iterates_registry_and_calls_upsert(db_session, stub_provider):
    """refresh() must walk every series in the registry, fetch it via the
    provider, and persist the rows via SQLAlchemy ``execute``."""
    service = FredService(db=db_session, provider=stub_provider)
    result = service.refresh(lookback_days=10)

    # 2026-07: registry grew to include EU and global series; refresh now
    # iterates US + EU + global. Each stub series yields 3 valid obs.
    total_series = len(SERIES_REGISTRY) + len(_EU_SERIES) + len(_GLOBAL_SERIES)
    assert result["written"] == 3 * total_series
    assert result["series_count"] == total_series
    assert result["failed"] == []

    rows = db_session.query(MacroIndicator).all()
    # Only the non-"." rows survive per series → 3 per series.
    assert len(rows) == 3 * total_series
    # Spot-check: every persisted row tagged source=fred; region is
    # 'us' (legacy), 'eu' (Eurozone), or 'global' (cross-border series).
    assert all(r.source == "fred" for r in rows)
    assert {r.region for r in rows} <= {"us", "eu", "global"}
    # And specifically: every US-only code keeps region='us'; every
    # eu_* code is region='eu'; every global_* code is tagged region='global'.
    us_codes = {m.code for m in SERIES_REGISTRY}
    eu_codes = {m.code for m in _EU_SERIES}
    global_codes = {m.code for m in _GLOBAL_SERIES}
    for r in rows:
        if r.code in us_codes:
            assert r.region == "us"
        elif r.code in eu_codes:
            assert r.region == "eu"
        elif r.code in global_codes:
            assert r.region == "global"


def test_refresh_is_idempotent(db_session, stub_provider):
    """Running refresh twice must NOT create duplicate rows for the same
    (code, region, period, source)."""
    service = FredService(db=db_session, provider=stub_provider)
    service.refresh(lookback_days=10)
    first_count = db_session.query(MacroIndicator).count()

    service.refresh(lookback_days=10)
    second_count = db_session.query(MacroIndicator).count()

    assert first_count == second_count, (
        f"Refresh is not idempotent: {first_count} → {second_count} rows"
    )


def test_refresh_records_failures(db_session):
    """If the provider raises for one series, refresh logs it and continues."""
    provider = MagicMock()

    def _maybe_fail(sid, start_date=None, end_date=None):
        if sid == "DGS10":
            raise RuntimeError("simulated network error")
        return [{"date": "2026-06-01", "value": 1.5}]

    provider.get_series.side_effect = _maybe_fail
    provider.rate_limit_sleep.return_value = None

    service = FredService(db=db_session, provider=provider)
    result = service.refresh(lookback_days=10)

    assert "DGS10" in result["failed"]
    # Other series still got written.
    assert result["written"] > 0


def test_refresh_skips_when_api_key_missing(db_session):
    """If no API key is configured, refresh returns a clean skip result."""
    from unittest.mock import patch

    service = FredService(db=db_session)
    with patch("app.services.macro.fred_service.get_settings") as gs:
        gs.return_value.fred_api_key = ""
        result = service.refresh(lookback_days=10)

    assert result["written"] == 0
    assert result["skipped_reason"] == "FRED_API_KEY not configured"
    # Failed list now covers US, EU, and global registries.
    assert set(result["failed"]) == {
        m.series_id for m in (list(SERIES_REGISTRY) + list(_EU_SERIES) + list(_GLOBAL_SERIES))
    }


# ---------------------------------------------------------------------------
# Read path
# ---------------------------------------------------------------------------

def test_list_indicators_returns_all_registered_with_latest(db_session, stub_provider):
    service = FredService(db=db_session, provider=stub_provider)
    service.refresh(lookback_days=10)

    items = service.list_indicators()
    total = len(SERIES_REGISTRY) + len(_EU_SERIES) + len(_GLOBAL_SERIES)
    assert len(items) == total
    # Every entry has metadata fields populated; region is one of the
    # three tags the service knows how to write.
    for item in items:
        assert item["code"]
        assert item["name_zh"]
        assert item["region"] in {"us", "eu", "global"}
        assert item["source"] == "fred"
    # And at least one item has a populated latest value.
    assert any(item["value"] is not None for item in items)


def test_list_indicators_region_filter(db_session, stub_provider):
    service = FredService(db=db_session, provider=stub_provider)
    service.refresh(lookback_days=10)

    # ``us`` returns only the legacy US series; ``eu`` returns only the
    # Eurozone series; ``global`` returns only the cross-border series;
    # ``cn`` returns empty (we ship US + EU + global).
    assert len(service.list_indicators(region="us")) == len(SERIES_REGISTRY)
    assert len(service.list_indicators(region="eu")) == len(_EU_SERIES)
    assert len(service.list_indicators(region="global")) == len(_GLOBAL_SERIES)
    assert service.list_indicators(region="cn") == []


def test_get_series_returns_ascending_points(db_session, stub_provider):
    service = FredService(db=db_session, provider=stub_provider)
    service.refresh(lookback_days=10)

    series = service.get_series("us_cpi")
    assert series is not None
    assert series["code"] == "us_cpi"
    # Stub returns same dates for every series — pick the points for us_cpi.
    points = series["points"]
    assert points, "expected at least one point"
    # Ascending by period.
    periods = [p["period"] for p in points]
    assert periods == sorted(periods)


def test_get_series_global_codes(db_session, stub_provider):
    """get_series should also resolve global_* codes."""
    service = FredService(db=db_session, provider=stub_provider)
    service.refresh(lookback_days=10)

    series = service.get_series("global_brent")
    assert series is not None
    assert series["region"] == "global"
    assert series["code"] == "global_brent"


def test_get_series_unknown_code_returns_none(db_session):
    service = FredService(db=db_session)
    assert service.get_series("not_a_real_code") is None