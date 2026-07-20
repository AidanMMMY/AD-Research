"""Shared pytest fixtures for end-to-end service tests.

Each test runs against a fresh in-memory SQLite database, seeded with
minimal but realistic data (ETFInfo rows, InstrumentDailyBar history,
indicator snapshots, etc.) so the services can be exercised end-to-end
without touching the dev or production database.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.etf import ETFIndicator, ETFInfo, InstrumentDailyBar
from app.models.etl import BacktestResult, Signal, StrategyConfig
from app.models.scoring import ETFScore, ScoreTemplate
from app.models.trading import (
    LiveTradeConfig,
    LiveTradeOrder,
    LiveTradePosition,
    PaperTradeAccount,
    PaperTradeOrder,
    PaperTradePosition,
)
from app.models.user import User


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    """Yield a fresh in-memory SQLite session with the full schema.

    Also clears the Redis cache to prevent stale data from prior test
    runs polluting category and screening queries.
    """
    _clear_screening_cache()

    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine)
    session = Session_()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
        # Clear again after the test so subsequent test files see a clean state
        _clear_screening_cache()


def _clear_screening_cache():
    """Wipe the screening and category-related Redis keys.

    The screening service caches under two prefixes:
      - ``etf:screen:*``  for screen() and screen_by_preset() results
      - ``etf:categories`` for get_categories() results
    """
    try:
        from app.core.redis_client import get_redis_client

        client = get_redis_client()
        for pattern in ("etf:screen:*", "etf:categories*"):
            for key in client.scan_iter(match=pattern):
                client.delete(key)
    except Exception:
        # Redis unavailable in this test environment — silently skip.
        pass


# ---------------------------------------------------------------------------
# Deterministic random generators
# ---------------------------------------------------------------------------


@pytest.fixture
def rng():
    """Seeded numpy RNG for reproducible price/indicator fixtures."""
    return np.random.default_rng(42)


# ---------------------------------------------------------------------------
# Price-series fixtures
# ---------------------------------------------------------------------------


def _build_price_series(
    code: str,
    n_days: int,
    start_price: float,
    drift: float,
    vol: float,
    seed: int,
) -> pd.DataFrame:
    """Build a deterministic OHLCV DataFrame for one instrument.

    Args:
        code: Instrument code (e.g. "510300.SH").
        n_days: Number of trading days.
        start_price: Initial close price.
        drift: Per-day expected log-return.
        vol: Per-day log-return stddev.
        seed: RNG seed.
    """
    rng = np.random.default_rng(seed)
    # Use a fixed business-day grid so trade_dates are realistic.
    dates = pd.bdate_range("2024-01-02", periods=n_days)
    log_rets = rng.normal(drift, vol, n_days)
    prices = start_price * np.exp(np.cumsum(log_rets))
    close = pd.Series(prices, index=dates)

    high = close * (1 + np.abs(rng.normal(0.005, 0.003, n_days)))
    low = close * (1 - np.abs(rng.normal(0.005, 0.003, n_days)))
    open_ = close.shift(1).fillna(close.iloc[0]) * (1 + rng.normal(0, 0.002, n_days))
    volume = rng.integers(1_000_000, 5_000_000, n_days)

    df = pd.DataFrame(
        {
            "trade_date": dates.date,
            "open": open_.values,
            "high": high.values,
            "low": low.values,
            "close": close.values,
            "volume": volume,
        }
    )
    df["adj_factor"] = 1.0
    df["amount"] = df["close"] * df["volume"]
    df["pre_close"] = df["close"].shift(1).fillna(df["close"].iloc[0])
    df["change_pct"] = (df["close"] - df["pre_close"]) / df["pre_close"] * 100
    df["is_synthetic"] = True
    return df


@pytest.fixture
def sample_price_series(rng):
    """50-day price history for a single synthetic instrument (510300.SH)."""
    return _build_price_series("510300.SH", 50, 100.0, 0.001, 0.02, 42)


@pytest.fixture
def sample_two_assets(rng):
    """Two-asset price history (A and B) for portfolio risk tests."""
    return {
        "A": _build_price_series("A.SH", 120, 100.0, 0.0005, 0.015, 1),
        "B": _build_price_series("B.SH", 120, 100.0, 0.001, 0.025, 2),
    }


# ---------------------------------------------------------------------------
# Indicator / scoring fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_indicators():
    """A single ETF indicator snapshot — raw metrics, not scores.

    Volatility, returns, and max drawdown are stored as decimals
    (0.05 ≈ 5%) per the 2026-07-01 risk-unit unification.
    """
    return {
        "return_1m": 0.05,
        "return_3m": 0.12,
        "return_1y": 0.25,
        "sharpe_1y": 1.5,
        "volatility_20d": 0.18,
        "max_drawdown_1y": -0.10,
        "rsi14": 55.0,
        "ma5": 101.0,
        "ma20": 100.0,
        "amount": 1_000_000.0,
    }


@pytest.fixture
def seeded_etf_universe(db_session):
    """Create 5 ETFs with one day of indicators + price history.

    Used by scoring and screening tests.  Each ETF has a distinct metric
    profile so percentile-based scoring produces non-trivial ranks.
    """
    profiles = [
        {
            "code": "510300.SH",
            "name": "CSI 300 ETF",
            "category": "股票型",
            "return_1m": 0.08,
            "return_3m": 0.18,
            "return_1y": 0.35,
            "sharpe_1y": 2.0,
            "volatility_20d": 0.15,
            "max_drawdown_1y": -0.08,
            "rsi14": 70.0,
            "amount": 2_000_000.0,
        },
        {
            "code": "510500.SH",
            "name": "CSI 500 ETF",
            "category": "股票型",
            "return_1m": 0.05,
            "return_3m": 0.12,
            "return_1y": 0.22,
            "sharpe_1y": 1.4,
            "volatility_20d": 0.18,
            "max_drawdown_1y": -0.10,
            "rsi14": 60.0,
            "amount": 1_500_000.0,
        },
        {
            "code": "511010.SH",
            "name": "Treasury Bond ETF",
            "category": "债券型",
            "return_1m": 0.005,
            "return_3m": 0.02,
            "return_1y": 0.06,
            "sharpe_1y": 0.9,
            "volatility_20d": 0.05,
            "max_drawdown_1y": -0.02,
            "rsi14": 45.0,
            "amount": 800_000.0,
        },
        {
            "code": "512760.SH",
            "name": "Tech ETF",
            "category": "股票型",
            "return_1m": 0.10,
            "return_3m": 0.25,
            "return_1y": 0.45,
            "sharpe_1y": 1.8,
            "volatility_20d": 0.25,
            "max_drawdown_1y": -0.18,
            "rsi14": 75.0,
            "amount": 3_000_000.0,
        },
        {
            "code": "513500.SH",
            "name": "S&P 500 ETF",
            "category": "商品型",
            "return_1m": 0.03,
            "return_3m": 0.08,
            "return_1y": 0.18,
            "sharpe_1y": 1.6,
            "volatility_20d": 0.12,
            "max_drawdown_1y": -0.07,
            "rsi14": 55.0,
            "amount": 1_800_000.0,
        },
    ]

    trade_date = date(2024, 6, 30)
    for p in profiles:
        db_session.add(
            ETFInfo(
                code=p["code"],
                name=p["name"],
                market="E2E_SH",  # Distinct market so cache keys don't collide
                category=p["category"],
                status="active",
            )
        )
        db_session.add(
            ETFIndicator(
                etf_code=p["code"],
                trade_date=trade_date,
                return_1m=Decimal(str(p["return_1m"])),
                return_3m=Decimal(str(p["return_3m"])),
                return_1y=Decimal(str(p["return_1y"])),
                sharpe_1y=Decimal(str(p["sharpe_1y"])),
                volatility_20d=Decimal(str(p["volatility_20d"])),
                max_drawdown_1y=Decimal(str(p["max_drawdown_1y"])),
                rsi14=Decimal(str(p["rsi14"])),
                ma5=Decimal("100.0"),
                ma20=Decimal("100.0"),
                amount=Decimal(str(p["amount"])),
            )
        )
        # 60-day price history per ETF
        df = _build_price_series(p["code"], 60, 100.0, 0.001, 0.02, hash(p["code"]) % 1000)
        for _, row in df.iterrows():
            db_session.add(
                InstrumentDailyBar(
                    etf_code=p["code"],
                    trade_date=row["trade_date"],
                    open=Decimal(str(round(row["open"], 4))),
                    high=Decimal(str(round(row["high"], 4))),
                    low=Decimal(str(round(row["low"], 4))),
                    close=Decimal(str(round(row["close"], 4))),
                    volume=int(row["volume"]),
                    amount=Decimal(str(round(row["amount"], 2))),
                    adj_factor=Decimal("1.0"),
                )
            )
    db_session.commit()
    return {"trade_date": trade_date, "codes": [p["code"] for p in profiles]}


# ---------------------------------------------------------------------------
# Test user (multi-tenant user_id columns are NOT NULL)
# ---------------------------------------------------------------------------


@pytest.fixture
def test_user(db_session):
    """A minimal users row so models with ``user_id nullable=False`` can be seeded."""
    user = User(
        username="e2e_tester",
        password_hash="not-a-real-hash",
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


# ---------------------------------------------------------------------------
# Strategy / backtest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def strategy_config(db_session, test_user):
    """A single momentum strategy persisted to the DB."""
    cfg = StrategyConfig(
        user_id=test_user.id,
        name="Momentum 20/5%",
        description="Momentum strategy used in e2e backtest",
        strategy_type="momentum",
        params={"momentum_window": 20, "threshold": 0.05, "holding_period": 20},
    )
    db_session.add(cfg)
    db_session.commit()
    return cfg


@pytest.fixture
def backtest_result(db_session, strategy_config):
    """A BacktestResult row with 3 trades and embedded metrics.

    Used by the attribution service e2e test.
    """
    trades = [
        {
            "entry_date": "2024-02-01",
            "exit_date": "2024-02-15",
            "entry_price": 100.0,
            "exit_price": 110.0,
            "pnl": 10.0,
            "pnl_pct": 0.10,
        },
        {
            "entry_date": "2024-03-01",
            "exit_date": "2024-03-10",
            "entry_price": 105.0,
            "exit_price": 102.0,
            "pnl": -3.0,
            "pnl_pct": -0.0286,
        },
        {
            "entry_date": "2024-04-01",
            "exit_date": "2024-04-20",
            "entry_price": 108.0,
            "exit_price": 115.0,
            "pnl": 7.0,
            "pnl_pct": 0.0648,
        },
    ]
    metrics = {
        "initial_capital": 100000.0,
        "final_nav": 114000.0,
        "total_return": 14.0,
        "annualized_return": 28.0,
        "max_drawdown": -5.0,
        "sharpe_ratio": 1.5,
        "win_rate": 66.67,
        "trade_count": 3,
        "trading_days": 120,
    }
    config_snapshot = {
        "etf_code": "510300.SH",
        "strategy_type": "momentum",
        "params": {"momentum_window": 20, "threshold": 0.05},
    }
    br = BacktestResult(
        user_id=strategy_config.user_id,
        strategy_id=strategy_config.id,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 6, 30),
        metrics=metrics,
        trades=trades,
        config_snapshot=config_snapshot,
    )
    db_session.add(br)
    db_session.commit()
    # Also seed the price history for benchmark comparison
    df = _build_price_series("510300.SH", 120, 100.0, 0.001, 0.02, 99)
    for _, row in df.iterrows():
        db_session.add(
            InstrumentDailyBar(
                etf_code="510300.SH",
                trade_date=row["trade_date"],
                open=Decimal(str(round(row["open"], 4))),
                high=Decimal(str(round(row["high"], 4))),
                low=Decimal(str(round(row["low"], 4))),
                close=Decimal(str(round(row["close"], 4))),
                volume=int(row["volume"]),
                amount=Decimal(str(round(row["amount"], 2))),
                adj_factor=Decimal("1.0"),
            )
        )
    db_session.commit()
    return br


# ---------------------------------------------------------------------------
# Live trading / risk-control fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def live_config(db_session, test_user):
    """A single LiveTradeConfig with conservative risk limits for tests."""
    cfg = LiveTradeConfig(
        user_id=test_user.id,
        name="E2E Test Config",
        is_testnet=True,
        is_enabled=True,
        max_order_value=Decimal("100"),
        max_daily_loss=Decimal("50"),
        max_daily_orders=5,
        allowed_symbols='["BTC.US", "ETH.US"]',
    )
    db_session.add(cfg)
    db_session.commit()
    return cfg


# ---------------------------------------------------------------------------
# BinanceProvider mock helpers (for paper-trading tests)
# ---------------------------------------------------------------------------


def make_provider_mock(price: float) -> Any:
    """Build a MagicMock that mimics BinanceProvider.fetch_realtime_quotes."""
    from unittest.mock import MagicMock

    df = pd.DataFrame(
        [
            {
                "etf_code": "BTC.US",
                "price": price,
                "price_change_pct": 0.0,
                "high": price,
                "low": price,
                "volume": 0,
                "amount": 0,
            }
        ]
    )
    mock = MagicMock()
    mock.fetch_realtime_quotes.return_value = df
    return mock


@pytest.fixture
def crypto_universe(db_session):
    """A minimal crypto universe (BTC.US + ETH.US) for paper-trading tests."""
    db_session.add(
        ETFInfo(
            code="BTC.US",
            name="Bitcoin",
            market="CRYPTO",
            category="Layer1",
            currency="USDT",
            instrument_type="CRYPTO",
            status="active",
        )
    )
    db_session.add(
        ETFInfo(
            code="ETH.US",
            name="Ethereum",
            market="CRYPTO",
            category="Layer1",
            currency="USDT",
            instrument_type="CRYPTO",
            status="active",
        )
    )
    db_session.commit()
    return ["BTC.US", "ETH.US"]


# ---------------------------------------------------------------------------
# Seeded score-template fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def default_template(db_session):
    """A single balanced score template used by scoring tests."""
    t = ScoreTemplate(
        name="E2E Balanced",
        description="Balanced weights for e2e tests",
        weights={
            "return": 0.3,
            "risk": 0.25,
            "sharpe": 0.25,
            "liquidity": 0.1,
            "trend": 0.1,
        },
        is_default=True,
    )
    db_session.add(t)
    db_session.commit()
    return t
