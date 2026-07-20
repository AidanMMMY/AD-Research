"""Tests for BinanceProvider host failover and the crypto daily ETL
empty-feed guard.

Regression coverage for the 2026-07 production incident where
``crypto_daily_etl`` logged ``success`` with ``records_count=0`` for days:
``api.binance.com`` is geo-blocked on the Aliyun ECS, every kline request
failed silently, and the empty DataFrame was recorded as a successful run.
"""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest
import requests

from app.core.exceptions import DataProviderError
from app.data.pipelines.crypto_daily import CryptoDailyPipeline
from app.data.providers.binance_provider import BinanceProvider
from app.models.etf import ETFInfo


def _kline(open_time_ms: int, open_px: float = 100.0, close_px: float = 101.0) -> list:
    """Build a Binance kline array (12 fields)."""
    return [
        open_time_ms,
        str(open_px),
        str(open_px + 2),
        str(open_px - 2),
        str(close_px),
        "123.0",
        open_time_ms + 86_399_999,
        "12345.0",
        42,
        "0",
        "0",
        "0",
    ]


class _FakeResponse:
    def __init__(self, payload) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.data.providers.binance_provider.time.sleep", lambda *_: None)


# ---------------------------------------------------------------------------
# Symbol mapping
# ---------------------------------------------------------------------------


def test_symbol_mapping_roundtrip() -> None:
    assert BinanceProvider.to_binance_symbol("BTC.US") == "BTCUSDT"
    assert BinanceProvider.from_binance_symbol("BTCUSDT") == "BTC.US"


# ---------------------------------------------------------------------------
# fetch_daily_bars
# ---------------------------------------------------------------------------


def test_fetch_daily_bars_uses_utc_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    open_ms = int(datetime(2026, 7, 18, tzinfo=UTC).timestamp() * 1000)

    def fake_get(url, params=None, timeout=30):
        return _FakeResponse([_kline(open_ms)])

    monkeypatch.setattr("app.data.providers.binance_provider.requests.get", fake_get)
    _no_sleep(monkeypatch)

    df = BinanceProvider().fetch_daily_bars(["BTC.US"], date(2026, 7, 18), date(2026, 7, 18))

    assert len(df) == 1
    # Daily candles open at 00:00 UTC; the trade date must not depend on
    # the container's local timezone.
    assert df.iloc[0]["trade_date"] == date(2026, 7, 18)
    assert df.iloc[0]["etf_code"] == "BTC.US"
    assert df.iloc[0]["close"] == 101.0


def test_fetch_daily_bars_fails_over_to_second_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    open_ms = int(datetime(2026, 7, 18, tzinfo=UTC).timestamp() * 1000)
    attempted: list[str] = []

    def fake_get(url, params=None, timeout=30):
        attempted.append(url)
        if url.startswith("https://api.binance.com"):
            raise requests.ConnectionError("geo-blocked")
        return _FakeResponse([_kline(open_ms)])

    monkeypatch.setattr("app.data.providers.binance_provider.requests.get", fake_get)
    _no_sleep(monkeypatch)

    df = BinanceProvider().fetch_daily_bars(["BTC.US"], date(2026, 7, 18), date(2026, 7, 18))

    assert not df.empty
    assert attempted[0].startswith("https://api.binance.com")
    assert attempted[1].startswith("https://data-api.binance.vision")


def test_fetch_daily_bars_raises_when_all_hosts_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url, params=None, timeout=30):
        raise requests.ConnectionError("unreachable")

    monkeypatch.setattr("app.data.providers.binance_provider.requests.get", fake_get)
    _no_sleep(monkeypatch)

    with pytest.raises(DataProviderError):
        BinanceProvider().fetch_daily_bars(
            ["BTC.US", "ETH.US"], date(2026, 7, 18), date(2026, 7, 18)
        )


def test_fetch_daily_bars_empty_candles_without_failures_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url, params=None, timeout=30):
        return _FakeResponse([])

    monkeypatch.setattr("app.data.providers.binance_provider.requests.get", fake_get)
    _no_sleep(monkeypatch)

    df = BinanceProvider().fetch_daily_bars(["BTC.US"], date(2026, 7, 18), date(2026, 7, 18))
    assert df.empty


# ---------------------------------------------------------------------------
# CryptoDailyPipeline empty-feed guard
# ---------------------------------------------------------------------------

_TARGET = date(2026, 7, 18)


def _bars(trade_date: date) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "etf_code": ["BTC.US"],
            "trade_date": [trade_date],
            "open": [100.0],
            "high": [102.0],
            "low": [98.0],
            "close": [101.0],
            "volume": [123.0],
            "amount": [12345.0],
            "change_pct": [1.0],
        }
    )


@pytest.fixture
def crypto_pipeline(db_session):
    db_session.add(
        ETFInfo(
            code="BTC.US",
            name="Bitcoin",
            market="CRYPTO",
            exchange="BINANCE",
            instrument_type="CRYPTO",
            status="active",
        )
    )
    db_session.commit()
    pipeline = CryptoDailyPipeline(db=db_session, target_date=_TARGET, seed_instruments=False)
    pipeline.provider = MagicMock()
    return pipeline


def test_extract_raises_when_provider_returns_empty(crypto_pipeline) -> None:
    crypto_pipeline.provider.fetch_daily_bars.return_value = pd.DataFrame()
    with pytest.raises(DataProviderError):
        crypto_pipeline.extract()


def test_extract_raises_when_target_date_missing(crypto_pipeline) -> None:
    crypto_pipeline.provider.fetch_daily_bars.return_value = _bars(_TARGET - timedelta(days=1))
    with pytest.raises(DataProviderError):
        crypto_pipeline.extract()


def test_extract_returns_only_target_date_rows(crypto_pipeline) -> None:
    df = pd.concat(
        [_bars(_TARGET - timedelta(days=1)), _bars(_TARGET)],
        ignore_index=True,
    )
    crypto_pipeline.provider.fetch_daily_bars.return_value = df

    out = crypto_pipeline.extract()

    assert len(out) == 1
    assert out.iloc[0]["trade_date"] == _TARGET
