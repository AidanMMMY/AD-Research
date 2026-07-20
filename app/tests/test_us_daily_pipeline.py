"""Tests for USDailyPipeline extract error handling and Tiingo failure modes.

Covers the 2026-07 US daily ETL outage class of bugs: when all data
sources return empty/fail, the pipeline must raise an explicit per-source
error instead of surfacing a misleading "Missing required columns"
validation failure.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.core.exceptions import DataProviderError
from app.data.pipelines.us_etf import USDailyPipeline
from app.data.providers.tiingo_provider import (
    _MAX_CONSECUTIVE_RATE_LIMITS,
    TiingoProvider,
)
from app.models.etf import ETFInfo, InstrumentDailyBar

START = date(2026, 7, 10)
END = date(2026, 7, 18)


def _seed_us_instrument(db) -> None:
    db.add(
        ETFInfo(
            code="SPY.US",
            name="SPDR S&P 500 ETF",
            market="US",
            status="active",
            instrument_type="ETF",
        )
    )
    db.add(
        InstrumentDailyBar(
            etf_code="SPY.US",
            trade_date=date(2026, 6, 30),
            open=1,
            high=1,
            low=1,
            close=1,
        )
    )
    db.commit()


def _make_pipeline(db):
    pipeline = USDailyPipeline(db, target_date=END)
    pipeline.provider = MagicMock()
    pipeline.provider.name = "tiingo"
    return pipeline


def _no_redis():
    raise RuntimeError("redis unavailable in tests")


# ---------------------------------------------------------------------------
# TiingoProvider failure handling
# ---------------------------------------------------------------------------


class TestTiingoProviderFailures:
    def test_auth_error_raises_with_http_status(self, monkeypatch):
        monkeypatch.setenv("TIINGO_API_KEY", "test-key")
        resp = MagicMock(status_code=401, text='{"detail":"Not authenticated"}')
        with (
            patch("app.data.providers.tiingo_provider.requests.get", return_value=resp),
            pytest.raises(DataProviderError, match="HTTP 401"),
        ):
            TiingoProvider().fetch_daily_bars(["SPY.US"], START, END)

    def test_aborts_batch_after_consecutive_429(self, monkeypatch):
        monkeypatch.setenv("TIINGO_API_KEY", "test-key")
        resp = MagicMock(status_code=429, text="too many requests")
        codes = ["A.US", "B.US", "C.US", "D.US", "E.US"]
        with patch(
            "app.data.providers.tiingo_provider.requests.get", return_value=resp
        ) as mock_get:
            df = TiingoProvider().fetch_daily_bars(codes, START, END)
        assert df.empty
        assert mock_get.call_count == _MAX_CONSECUTIVE_RATE_LIMITS

    def test_parses_successful_response(self, monkeypatch):
        monkeypatch.setenv("TIINGO_API_KEY", "test-key")
        resp = MagicMock(status_code=200)
        resp.json.return_value = [
            {
                "date": "2026-07-17T00:00:00.000Z",
                "open": 750.0,
                "high": 755.0,
                "low": 748.0,
                "close": 754.0,
                "volume": 42000000,
                "adjClose": 754.0,
            }
        ]
        with (
            patch("app.data.providers.tiingo_provider.requests.get", return_value=resp),
            patch("app.data.providers.tiingo_provider.time.sleep"),
        ):
            df = TiingoProvider().fetch_daily_bars(["SPY.US"], START, END)
        assert len(df) == 1
        row = df.iloc[0]
        assert row["etf_code"] == "SPY.US"
        assert row["trade_date"] == date(2026, 7, 17)
        assert row["close"] == 754.0
        assert row["adj_factor"] == 1.0


# ---------------------------------------------------------------------------
# USDailyPipeline extract error propagation
# ---------------------------------------------------------------------------


class TestUSDailyExtractErrors:
    def test_raises_per_source_error_when_all_sources_empty(self, db_session, monkeypatch):
        _seed_us_instrument(db_session)
        monkeypatch.setattr("app.data.pipelines.us_etf.get_redis_client", _no_redis)
        pipeline = _make_pipeline(db_session)
        pipeline.provider.fetch_daily_bars.return_value = pd.DataFrame()

        with patch("app.data.pipelines.us_etf.YFinanceProvider") as mock_yf:
            mock_yf.return_value.fetch_daily_bars.return_value = pd.DataFrame()
            with pytest.raises(DataProviderError) as exc_info:
                pipeline.extract()

        msg = str(exc_info.value)
        assert "all sources returned no data" in msg
        assert "tiingo: returned empty" in msg
        assert "yfinance: returned empty" in msg

    def test_provider_exception_is_surfaced(self, db_session, monkeypatch):
        _seed_us_instrument(db_session)
        monkeypatch.setattr("app.data.pipelines.us_etf.get_redis_client", _no_redis)
        pipeline = _make_pipeline(db_session)
        pipeline.provider.fetch_daily_bars.side_effect = DataProviderError(
            "tiingo auth failed (HTTP 401) for SPY"
        )

        with patch("app.data.pipelines.us_etf.YFinanceProvider") as mock_yf:
            mock_yf.return_value.fetch_daily_bars.return_value = pd.DataFrame()
            with pytest.raises(DataProviderError) as exc_info:
                pipeline.extract()

        assert "HTTP 401" in str(exc_info.value)

    def test_extract_returns_tiingo_rows_on_success(self, db_session, monkeypatch):
        _seed_us_instrument(db_session)
        monkeypatch.setattr("app.data.pipelines.us_etf.get_redis_client", _no_redis)
        pipeline = _make_pipeline(db_session)
        pipeline.provider.fetch_daily_bars.return_value = pd.DataFrame(
            [
                {
                    "etf_code": "SPY.US",
                    "trade_date": END,
                    "open": 750.0,
                    "high": 755.0,
                    "low": 748.0,
                    "close": 754.0,
                    "volume": 42000000,
                    "amount": 1.0,
                    "adj_factor": 1.0,
                }
            ]
        )

        with patch("app.data.pipelines.us_etf.YFinanceProvider") as mock_yf:
            df = pipeline.extract()
            # Tiingo covered the only symbol, so yfinance is not needed.
            mock_yf.return_value.fetch_daily_bars.assert_not_called()

        assert len(df) == 1
        assert df.iloc[0]["etf_code"] == "SPY.US"
