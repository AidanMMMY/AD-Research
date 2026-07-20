"""Tests for PaperTradingService.

Mocks the BinanceProvider so tests run hermetically.  Covers account
lifecycle, order placement, position updates and PnL summary.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.models.etf import ETFInfo
from app.models.trading import PaperTradeAccount, PaperTradeOrder, PaperTradePosition
from app.services.paper_trading_service import PaperTradingError, PaperTradingService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider_mock(price: float = 100.0) -> MagicMock:
    """Build a mock provider that returns a single-quote DataFrame."""
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
def seeded_db(db_session):
    """Create an instrument row for tests."""
    db_session.add(
        ETFInfo(
            code="BTC.US",
            name="Bitcoin",
            category="Layer1",
            market="CRYPTO",
        )
    )
    db_session.commit()
    return db_session


# ---------------------------------------------------------------------------
# Account lifecycle
# ---------------------------------------------------------------------------


def test_create_account_defaults(seeded_db):
    svc = PaperTradingService(seeded_db)
    with patch.object(
        PaperTradingService, "_get_provider_for_code", return_value=_make_provider_mock(100)
    ):
        account = svc.create_account("Main", Decimal("5000"), user_id=1)
    assert account.id is not None
    assert account.cash == Decimal("5000")
    assert account.initial_balance == Decimal("5000")
    assert account.status == "active"


def test_get_account_excludes_archived(seeded_db):
    svc = PaperTradingService(seeded_db)
    a = svc.create_account("A", Decimal("1000"), user_id=1)
    svc.archive_account(a.id)
    assert svc.get_account(a.id) is None
    assert svc.get_accounts() == []


def test_archive_unknown_account_returns_false(seeded_db):
    svc = PaperTradingService(seeded_db)
    assert svc.archive_account(9999) is False


# ---------------------------------------------------------------------------
# Order placement
# ---------------------------------------------------------------------------


def test_buy_order_reduces_cash_and_creates_position(seeded_db):
    svc = PaperTradingService(seeded_db)
    account = svc.create_account("X", Decimal("10000"), user_id=1)
    with patch.object(
        PaperTradingService, "_get_provider_for_code", return_value=_make_provider_mock(100)
    ):
        order = svc.place_order(account.id, "BTC.US", "BUY", Decimal("0.1"))
    assert order.status == "filled"
    assert order.filled_quantity == Decimal("0.1")
    seeded_db.refresh(account)
    assert account.cash == Decimal("9990")  # 10000 - 100*0.1
    pos = (
        seeded_db.query(PaperTradePosition)
        .filter(
            PaperTradePosition.account_id == account.id,
            PaperTradePosition.instrument_code == "BTC.US",
        )
        .first()
    )
    assert pos is not None
    assert float(pos.quantity) == pytest.approx(0.1, rel=1e-6)
    assert float(pos.avg_cost) == pytest.approx(100.0, rel=1e-6)


def test_buy_insufficient_cash_raises(seeded_db):
    svc = PaperTradingService(seeded_db)
    account = svc.create_account("Y", Decimal("10"), user_id=1)  # very little cash
    with patch.object(
        PaperTradingService, "_get_provider_for_code", return_value=_make_provider_mock(100)
    ):
        with pytest.raises(PaperTradingError, match="Insufficient cash"):
            svc.place_order(account.id, "BTC.US", "BUY", Decimal("1"))


def test_buy_unknown_instrument_raises(seeded_db):
    svc = PaperTradingService(seeded_db)
    account = svc.create_account("Z", Decimal("10000"), user_id=1)
    with patch.object(
        PaperTradingService, "_get_provider_for_code", return_value=_make_provider_mock(100)
    ):
        with pytest.raises(PaperTradingError, match="not found"):
            svc.place_order(account.id, "GHOST.US", "BUY", Decimal("0.1"))


def test_sell_reduces_position_and_realises_pnl(seeded_db):
    svc = PaperTradingService(seeded_db)
    account = svc.create_account("S", Decimal("10000"), user_id=1)
    # BUY at 100, then SELL at 120 -> +$2 realised PnL
    with patch.object(
        PaperTradingService, "_get_provider_for_code", return_value=_make_provider_mock(100)
    ):
        svc.place_order(account.id, "BTC.US", "BUY", Decimal("0.1"))
    with patch.object(
        PaperTradingService, "_get_provider_for_code", return_value=_make_provider_mock(120)
    ):
        sell = svc.place_order(account.id, "BTC.US", "SELL", Decimal("0.1"))
    assert sell.status == "filled"
    pos = (
        seeded_db.query(PaperTradePosition)
        .filter(
            PaperTradePosition.account_id == account.id,
            PaperTradePosition.instrument_code == "BTC.US",
        )
        .first()
    )
    assert pos.quantity == Decimal("0")
    # realized_pnl should be positive (0.1 * (120 - 100) = 2)
    assert float(pos.realized_pnl) == pytest.approx(2.0, rel=1e-6)


def test_sell_more_than_held_raises(seeded_db):
    svc = PaperTradingService(seeded_db)
    account = svc.create_account("Q", Decimal("10000"), user_id=1)
    with patch.object(
        PaperTradingService, "_get_provider_for_code", return_value=_make_provider_mock(100)
    ):
        svc.place_order(account.id, "BTC.US", "BUY", Decimal("0.1"))
        with pytest.raises(PaperTradingError, match="Insufficient position"):
            svc.place_order(account.id, "BTC.US", "SELL", Decimal("0.5"))


# ---------------------------------------------------------------------------
# PnL summary
# ---------------------------------------------------------------------------


def test_pnl_summary_no_trades(seeded_db):
    svc = PaperTradingService(seeded_db)
    account = svc.create_account("P", Decimal("1000"), user_id=1)
    with patch.object(
        PaperTradingService, "_get_provider_for_code", return_value=_make_provider_mock(100)
    ):
        summary = svc.get_pnl_summary(account.id)
    assert summary["trade_count"] == 0
    assert summary["cash"] == Decimal("1000")
    assert summary["total_pnl"] == Decimal("0")
    assert summary["win_rate"] is None


def test_pnl_summary_after_buy(seeded_db):
    svc = PaperTradingService(seeded_db)
    account = svc.create_account("P2", Decimal("10000"), user_id=1)
    with patch.object(
        PaperTradingService, "_get_provider_for_code", return_value=_make_provider_mock(100)
    ):
        svc.place_order(account.id, "BTC.US", "BUY", Decimal("0.5"))
    with patch.object(
        PaperTradingService, "_get_provider_for_code", return_value=_make_provider_mock(150)
    ):
        summary = svc.get_pnl_summary(account.id)
    assert summary["trade_count"] == 1
    # Unrealized PnL = 0.5 * (150 - 100) = 25
    assert float(summary["unrealized_pnl"]) == pytest.approx(25.0, rel=1e-6)
    # Cash was reduced by 50
    assert float(summary["cash"]) == pytest.approx(9950.0, rel=1e-6)


def test_pnl_summary_for_unknown_account_raises(seeded_db):
    svc = PaperTradingService(seeded_db)
    with pytest.raises(PaperTradingError):
        svc.get_pnl_summary(9999)
