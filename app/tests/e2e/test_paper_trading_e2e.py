"""End-to-end test for PaperTradingService.

Exercises the full order lifecycle with a mocked Binance price source.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services.paper_trading_service import (
    PaperTradingError,
    PaperTradingService,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _provider(price: float):
    """Build a BinanceProvider mock that returns ``price`` for every quote."""
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


# ---------------------------------------------------------------------------
# Full BUY -> SELL lifecycle
# ---------------------------------------------------------------------------


def test_paper_trading_full_buy_sell_lifecycle(db_session, crypto_universe):
    """BUY at 100, SELL at 120 -> +20 USDT realised PnL on 0.1 BTC."""
    svc = PaperTradingService(db_session)
    account = svc.create_account("E2E", Decimal("10000"))

    # BUY 0.1 BTC @ 100
    with patch.object(PaperTradingService, "provider", new=_provider(100.0)):
        buy = svc.place_order(account.id, "BTC.US", "BUY", Decimal("0.1"))
    assert buy.status == "filled"
    db_session.refresh(account)
    assert account.cash == Decimal("9990")  # 10000 - 100 * 0.1

    # SELL 0.1 BTC @ 120
    with patch.object(PaperTradingService, "provider", new=_provider(120.0)):
        sell = svc.place_order(account.id, "BTC.US", "SELL", Decimal("0.1"))
    assert sell.status == "filled"
    db_session.refresh(account)
    # 9990 + 120 * 0.1 = 10002
    assert account.cash == Decimal("10002")

    # PnL summary: realised = 0.1 * (120 - 100) = +2 USDT
    with patch.object(PaperTradingService, "provider", new=_provider(120.0)):
        summary = svc.get_pnl_summary(account.id)
    assert float(summary["realized_pnl"]) == pytest.approx(2.0, rel=1e-6)
    assert summary["trade_count"] == 2
    # Win count: 1 (the round-trip was profitable)
    assert summary["win_count"] == 1
    assert float(summary["win_rate"]) == pytest.approx(1.0, rel=1e-6)


def test_paper_trading_open_position_unrealized_pnl(db_session, crypto_universe):
    """After BUY @ 100, current price 150 -> unrealized PnL = 0.5 * 50 = 25."""
    svc = PaperTradingService(db_session)
    account = svc.create_account("E2E", Decimal("10000"))

    with patch.object(PaperTradingService, "provider", new=_provider(100.0)):
        svc.place_order(account.id, "BTC.US", "BUY", Decimal("0.5"))

    with patch.object(PaperTradingService, "provider", new=_provider(150.0)):
        summary = svc.get_pnl_summary(account.id)
    assert float(summary["unrealized_pnl"]) == pytest.approx(25.0, rel=1e-6)
    assert summary["realized_pnl"] == Decimal("0")
    # Total equity = 10000 - 50 (cash) + 75 (market value) = 10025
    assert float(summary["total_equity"]) == pytest.approx(10025.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Order validation
# ---------------------------------------------------------------------------


def test_paper_trading_insufficient_cash_raises(db_session, crypto_universe):
    """BUY exceeding cash should raise PaperTradingError."""
    svc = PaperTradingService(db_session)
    account = svc.create_account("Small", Decimal("10"))
    with patch.object(PaperTradingService, "provider", new=_provider(100.0)):
        with pytest.raises(PaperTradingError, match="Insufficient cash"):
            svc.place_order(account.id, "BTC.US", "BUY", Decimal("1"))


def test_paper_trading_insufficient_position_raises(db_session, crypto_universe):
    """SELL with no position should raise PaperTradingError."""
    svc = PaperTradingService(db_session)
    account = svc.create_account("NoPos", Decimal("10000"))
    with patch.object(PaperTradingService, "provider", new=_provider(100.0)):
        with pytest.raises(PaperTradingError, match="Insufficient position"):
            svc.place_order(account.id, "BTC.US", "SELL", Decimal("0.1"))


def test_paper_trading_unknown_instrument_raises(db_session):
    """BUY on a code that doesn't exist in ETFInfo should raise."""
    svc = PaperTradingService(db_session)
    account = svc.create_account("Ghost", Decimal("10000"))
    with patch.object(PaperTradingService, "provider", new=_provider(100.0)):
        with pytest.raises(PaperTradingError, match="not found"):
            svc.place_order(account.id, "GHOST.US", "BUY", Decimal("0.1"))


# ---------------------------------------------------------------------------
# Account lifecycle
# ---------------------------------------------------------------------------


def test_paper_trading_archive_excludes_account(db_session, crypto_universe):
    """archive_account should remove account from active listings."""
    svc = PaperTradingService(db_session)
    a1 = svc.create_account("Active", Decimal("1000"))
    a2 = svc.create_account("ToArchive", Decimal("1000"))
    assert {a.id for a in svc.get_accounts()} == {a1.id, a2.id}

    assert svc.archive_account(a2.id) is True
    active_ids = {a.id for a in svc.get_accounts()}
    assert a2.id not in active_ids
    assert a1.id in active_ids
    assert svc.get_account(a2.id) is None


def test_paper_trading_position_aggregation_vwap(db_session, crypto_universe):
    """Two BUYs at different prices should produce a VWAP avg_cost."""
    svc = PaperTradingService(db_session)
    account = svc.create_account("VWAP", Decimal("100000"))

    with patch.object(PaperTradingService, "provider", new=_provider(100.0)):
        svc.place_order(account.id, "BTC.US", "BUY", Decimal("1"))
    with patch.object(PaperTradingService, "provider", new=_provider(200.0)):
        svc.place_order(account.id, "BTC.US", "BUY", Decimal("1"))

    with patch.object(PaperTradingService, "provider", new=_provider(200.0)):
        positions = svc.get_positions(account.id)
    pos = next(p for p in positions if p.instrument_code == "BTC.US")
    # VWAP = (1 * 100 + 1 * 200) / 2 = 150
    assert float(pos.avg_cost) == pytest.approx(150.0, rel=1e-6)
    assert float(pos.quantity) == pytest.approx(2.0, rel=1e-6)
