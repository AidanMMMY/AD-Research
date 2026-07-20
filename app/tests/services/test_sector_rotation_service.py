"""Unit tests for ``SectorRotationService``.

These tests are DB-backed with an in-memory SQLite engine so they exercise
real aggregation and look-back logic without hitting the network/router layer.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.etf import ETFIndicator, ETFInfo
from app.services.sector_rotation_service import SectorRotationService


@pytest.fixture
def sr_engine():
    """In-memory SQLite engine with StaticPool for deterministic isolation."""
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
    """SQLAlchemy session bound to the in-memory engine."""
    SessionLocal = sessionmaker(bind=sr_engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def service(sr_session):
    """A ``SectorRotationService`` wired to the in-memory session."""
    return SectorRotationService(sr_session)


# ---------------------------------------------------------------------------
# Relative strength (excess return) tests
# ---------------------------------------------------------------------------


class _InstrumentProfile:
    """Simple container for seed data."""

    def __init__(
        self,
        code: str,
        sector: str,
        instrument_type: str = "STOCK",
        return_1m: float = 0.0,
    ):
        self.code = code
        self.name = f"{code} name"
        self.sector = sector
        self.instrument_type = instrument_type
        self.return_1m = return_1m


def _seed_universe(session, profiles: list[_InstrumentProfile], trade_date: date):
    """Insert ETFInfo + ETFIndicator rows for a single trade date."""
    for p in profiles:
        session.add(
            ETFInfo(
                code=p.code,
                name=p.name,
                market="A股",
                instrument_type=p.instrument_type,
                sector=p.sector,
                status="active",
            )
        )
        session.add(
            ETFIndicator(
                etf_code=p.code,
                trade_date=trade_date,
                return_1w=Decimal("0.0"),
                return_1m=Decimal(str(p.return_1m)),
                return_3m=Decimal(str(p.return_1m * 3)),  # arbitrary, keeps shape valid
                return_6m=Decimal(str(p.return_1m * 6)),
                return_1y=Decimal(str(p.return_1m * 12)),
                sharpe_1y=Decimal("1.0"),
                volatility_20d=Decimal("10.0"),
                max_drawdown_1y=Decimal("-5.0"),
                rsi14=Decimal("50.0"),
                ma5=Decimal("100.0"),
                ma20=Decimal("100.0"),
                amount=Decimal("1000000.0"),
            )
        )
    session.commit()


def test_relative_strength_is_excess_return_in_bear_market(service, sr_session):
    """When the market is negative, the strongest sector still has RS > 0."""
    d = date(2024, 6, 30)
    # All sectors decline, but IT declines less than the market average.
    # Equal-weight market average = (-1 + -9) / 2 = -5.0
    profiles = [
        _InstrumentProfile("IT1", "Information Technology", return_1m=-1.0),
        _InstrumentProfile("IT2", "Information Technology", return_1m=-1.0),
        _InstrumentProfile("HC1", "Health Care", return_1m=-9.0),
        _InstrumentProfile("HC2", "Health Care", return_1m=-9.0),
    ]
    _seed_universe(sr_session, profiles, d)

    result = service.analyze_sectors(d)
    sectors = {s["sector"]: s for s in result["sectors"]}

    assert sectors["Information Technology"]["relative_strength_1m"] == pytest.approx(
        4.0, abs=1e-4
    )
    assert sectors["Health Care"]["relative_strength_1m"] == pytest.approx(
        -4.0, abs=1e-4
    )
    # Excess-return ordering must match the expected relative strength ranking.
    assert (
        sectors["Information Technology"]["relative_strength_1m"]
        > sectors["Health Care"]["relative_strength_1m"]
    )


# ---------------------------------------------------------------------------
# Rotation-signal window tests
# ---------------------------------------------------------------------------


def _seed_daily_history(session, sectors, dates, make_return):
    """Seed one instrument per sector for each trade date."""
    for sector, code in sectors.items():
        session.add(
            ETFInfo(
                code=code,
                name=f"{code} {sector}",
                market="A股",
                instrument_type="STOCK",
                sector=sector,
                status="active",
            )
        )
        for td in dates:
            session.add(
                ETFIndicator(
                    etf_code=code,
                    trade_date=td,
                    return_1w=Decimal("0.0"),
                    return_1m=Decimal(str(make_return(sector, td))),
                    return_3m=Decimal("0.0"),
                    return_6m=Decimal("0.0"),
                    return_1y=Decimal("0.0"),
                    sharpe_1y=Decimal("1.0"),
                    volatility_20d=Decimal("10.0"),
                    max_drawdown_1y=Decimal("-5.0"),
                    rsi14=Decimal("50.0"),
                    ma5=Decimal("100.0"),
                    ma20=Decimal("100.0"),
                    amount=Decimal("1000000.0"),
                )
            )
    session.commit()


def test_rotation_signals_detect_three_plus_rank_changes(service, sr_session):
    """A ≥3 rank swing vs the 5-day lookback emits a rotation signal."""
    start = date(2024, 6, 3)
    dates = [start + timedelta(days=i) for i in range(6)]

    sectors = {
        "Information Technology": "IT0001",
        "Health Care": "HC0001",
        "Financials": "FIN001",
        "Energy": "ENE001",
    }

    def make_return(sector, td):
        # Lookback date (index 0): ranks 1=HC, 2=FIN, 3=ENE, 4=IT
        # (returns are decimals, e.g. 0.12 = 12%)
        if td == dates[0]:
            return {
                "Health Care": 0.12,
                "Financials": 0.09,
                "Energy": 0.06,
                "Information Technology": 0.01,
            }[sector]
        # Current date (index 5): ranks 1=IT, 2=ENE, 3=FIN, 4=HC
        if td == dates[5]:
            return {
                "Information Technology": 0.10,
                "Energy": 0.07,
                "Financials": 0.04,
                "Health Care": 0.01,
            }[sector]
        return 0.05

    _seed_daily_history(sr_session, sectors, dates, make_return)

    result = service.analyze_sectors(dates[-1])
    signals = {s["sector"]: s for s in result["rotation_signals"]}

    # IT: prev_rank 4 -> current_rank 1, change = +3 -> up signal
    assert "Information Technology" in signals
    assert signals["Information Technology"]["type"] == "up"
    assert signals["Information Technology"]["rank_change"] == 3
    assert signals["Information Technology"]["previous_rank"] == 4
    assert signals["Information Technology"]["current_rank"] == 1

    # HC: prev_rank 1 -> current_rank 4, change = -3 -> down signal
    assert "Health Care" in signals
    assert signals["Health Care"]["type"] == "down"
    assert signals["Health Care"]["rank_change"] == -3
    assert signals["Health Care"]["previous_rank"] == 1
    assert signals["Health Care"]["current_rank"] == 4

    # Make sure the intermediate dates do not affect the result: if the old
    # adjacent-day logic had been used, the signal would reference the previous
    # day (index 4) where all sectors are equal (5.0) and no signals would be
    # emitted.


def test_rotation_signals_skipped_with_insufficient_history(service, sr_session):
    """If fewer than 5 prior trading days exist, no signals are emitted."""
    d = date(2024, 6, 30)
    # Only 1 prior trading day seeded, so the 5-day lookback cannot be resolved.
    _seed_daily_history(
        sr_session,
        {"Information Technology": "IT1", "Health Care": "HC1"},
        [d - timedelta(days=1), d],
        lambda sector, td: 5.0,
    )

    result = service.analyze_sectors(d)
    assert result["rotation_signals"] == []


# ---------------------------------------------------------------------------
# Corrupt-value (missing-value sentinel / dirty adjustment) filtering tests
# ---------------------------------------------------------------------------

#: The missing-value sentinel observed in production indicator rows.
_SENTINEL = -1e9


def test_market_avg_excludes_sentinel_returns(service, sr_session):
    """Sentinel / out-of-range returns must not pollute sector or market averages."""
    d = date(2024, 6, 30)
    profiles = [
        _InstrumentProfile("IT1", "Information Technology", return_1m=2.0),
        _InstrumentProfile("IT2", "Information Technology", return_1m=4.0),
        _InstrumentProfile("IT3", "Information Technology", return_1m=_SENTINEL),
        _InstrumentProfile("HC1", "Health Care", return_1m=-2.0),
    ]
    _seed_universe(sr_session, profiles, d)

    result = service.analyze_sectors(d)

    # Market average is computed from the sane values only: (2 + 4 - 2) / 3.
    assert result["market_avg"]["return_1m"] == pytest.approx(4.0 / 3.0, abs=1e-4)

    sectors = {s["sector"]: s for s in result["sectors"]}
    # The sentinel row is excluded from the IT bucket: (2 + 4) / 2 = 3.0.
    # (Note: _seed_universe sets return_3m/6m/1y = k * return_1m, so the
    # sentinel row's other periods are filtered by the same guard.)
    assert sectors["Information Technology"]["return_1m"] == pytest.approx(3.0, abs=1e-4)
    assert sectors["Health Care"]["return_1m"] == pytest.approx(-2.0, abs=1e-4)
    # RS uses the clean market average: 3.0 - 4/3.
    assert sectors["Information Technology"]["relative_strength_1m"] == pytest.approx(
        3.0 - 4.0 / 3.0, abs=1e-4
    )


def test_constituents_sentinel_returns_output_none(service, sr_session):
    """Constituent rows surface corrupt returns as None (UI shows '-'), never raw values."""
    d = date(2024, 6, 30)
    profiles = [
        _InstrumentProfile("IT1", "Information Technology", return_1m=2.0),
        _InstrumentProfile("IT3", "Information Technology", return_1m=_SENTINEL),
    ]
    _seed_universe(sr_session, profiles, d)

    result = service.get_sector_constituents("Information Technology", trade_date=d)
    items = {i["code"]: i for i in result["items"]}

    assert items["IT1"]["return_1m"] == pytest.approx(2.0, abs=1e-4)
    assert items["IT3"]["return_1m"] is None
    # The sentinel also leaks into 3m/6m/1y via _seed_universe's k * return_1m;
    # every period must be masked.
    assert items["IT3"]["return_3m"] is None
    assert items["IT3"]["return_1y"] is None


def test_prev_returns_sentinel_excluded_from_rotation_ranking(service, sr_session):
    """A sentinel on the lookback date must not shift the previous-period rank."""
    start = date(2024, 6, 3)
    dates = [start + timedelta(days=i) for i in range(6)]

    sectors = {
        "Information Technology": "IT0001",
        "Health Care": "HC0001",
        "Financials": "FIN001",
    }

    def make_return(sector, td):
        # Lookback date: HC holds the sentinel; without filtering HC would
        # rank last (avg -1e9) instead of first.
        if td == dates[0]:
            return {
                "Health Care": _SENTINEL,
                "Financials": 9.0,
                "Information Technology": 1.0,
            }[sector]
        if td == dates[5]:
            return {
                "Information Technology": 10.0,
                "Health Care": 8.0,
                "Financials": 4.0,
            }[sector]
        return 5.0

    _seed_daily_history(sr_session, sectors, dates, make_return)

    result = service.analyze_sectors(dates[-1])
    signals = {s["sector"]: s for s in result["rotation_signals"]}

    # Without the sentinel, HC would rank 1st on the lookback date. With the
    # guard, HC has no sane lookback value, so it gets no previous rank and
    # emits no signal.
    assert "Health Care" not in signals
    # IT: prev ranks among sane sectors are FIN=1, IT=2 → current ranks
    # IT=1, HC=2, FIN=3 → change = 2 - 1 = +1, below the ±3 threshold.
    assert "Information Technology" not in signals
