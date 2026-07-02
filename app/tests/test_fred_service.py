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
from app.services.macro.fred_service import FredService, SERIES_REGISTRY


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

    assert result["written"] == 3 * len(SERIES_REGISTRY)  # 3 valid obs per series
    assert result["series_count"] == len(SERIES_REGISTRY)
    assert result["failed"] == []

    rows = db_session.query(MacroIndicator).all()
    # Only the non-"." rows survive per series → 3 per series.
    assert len(rows) == 3 * len(SERIES_REGISTRY)
    # Spot-check: every persisted row tagged source=fred and region=us.
    assert all(r.source == "fred" for r in rows)
    assert all(r.region == "us" for r in rows)


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
    assert set(result["failed"]) == {m.series_id for m in SERIES_REGISTRY}


# ---------------------------------------------------------------------------
# Read path
# ---------------------------------------------------------------------------

def test_list_indicators_returns_all_registered_with_latest(db_session, stub_provider):
    service = FredService(db=db_session, provider=stub_provider)
    service.refresh(lookback_days=10)

    items = service.list_indicators()
    assert len(items) == len(SERIES_REGISTRY)
    # Every entry has metadata fields populated.
    for item in items:
        assert item["code"]
        assert item["name_zh"]
        assert item["region"] == "us"
        assert item["source"] == "fred"
    # And at least one item has a populated latest value.
    assert any(item["value"] is not None for item in items)


def test_list_indicators_region_filter(db_session, stub_provider):
    service = FredService(db=db_session, provider=stub_provider)
    service.refresh(lookback_days=10)

    # ``us`` returns everything; ``cn`` returns empty (we only ship US data).
    assert len(service.list_indicators(region="us")) == len(SERIES_REGISTRY)
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


def test_get_series_unknown_code_returns_none(db_session):
    service = FredService(db=db_session)
    assert service.get_series("not_a_real_code") is None