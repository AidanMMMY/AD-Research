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
from app.data.providers.sina_us_provider import SinaUSProvider
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

        with (
            patch("app.data.pipelines.us_etf.YFinanceProvider") as mock_yf,
            patch("app.data.pipelines.us_etf.SinaUSProvider") as mock_sina,
        ):
            mock_yf.return_value.fetch_daily_bars.return_value = pd.DataFrame()
            mock_sina.return_value.fetch_daily_bars.return_value = pd.DataFrame()
            with pytest.raises(DataProviderError) as exc_info:
                pipeline.extract()

        msg = str(exc_info.value)
        assert "all sources returned no data" in msg
        assert "tiingo: returned empty" in msg
        assert "yfinance: returned empty" in msg
        assert "sina_us: returned empty" in msg

    def test_provider_exception_is_surfaced(self, db_session, monkeypatch):
        _seed_us_instrument(db_session)
        monkeypatch.setattr("app.data.pipelines.us_etf.get_redis_client", _no_redis)
        pipeline = _make_pipeline(db_session)
        pipeline.provider.fetch_daily_bars.side_effect = DataProviderError(
            "tiingo auth failed (HTTP 401) for SPY"
        )

        with (
            patch("app.data.pipelines.us_etf.YFinanceProvider") as mock_yf,
            patch("app.data.pipelines.us_etf.SinaUSProvider") as mock_sina,
        ):
            mock_yf.return_value.fetch_daily_bars.return_value = pd.DataFrame()
            mock_sina.return_value.fetch_daily_bars.return_value = pd.DataFrame()
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

        with (
            patch("app.data.pipelines.us_etf.YFinanceProvider") as mock_yf,
            patch("app.data.pipelines.us_etf.SinaUSProvider") as mock_sina,
        ):
            df = pipeline.extract()
            # Tiingo covered the only symbol, so fallbacks are not needed.
            mock_yf.return_value.fetch_daily_bars.assert_not_called()
            mock_sina.return_value.fetch_daily_bars.assert_not_called()

        assert len(df) == 1
        assert df.iloc[0]["etf_code"] == "SPY.US"


# ---------------------------------------------------------------------------
# SinaUSProvider (akshare stock_us_daily) behaviour
# ---------------------------------------------------------------------------


def _sina_raw_frame() -> pd.DataFrame:
    """Raw frame as returned by ak.stock_us_daily(adjust="")."""
    return pd.DataFrame(
        {
            "date": [date(2026, 7, 9), date(2026, 7, 17), date(2026, 7, 18)],
            "open": [700.0, 742.0, 750.0],
            "high": [705.0, 747.0, 755.0],
            "low": [698.0, 740.0, 748.0],
            "close": [702.0, 743.0, 754.0],
            "volume": [1000.0, 2000.0, 3000.0],
        }
    )


class TestSinaUSProvider:
    def test_converts_symbol_and_filters_date_range(self):
        with (
            patch(
                "app.data.providers.sina_us_provider.ak.stock_us_daily",
                return_value=_sina_raw_frame(),
            ) as mock_call,
            patch("app.data.providers.sina_us_provider.time.sleep"),
        ):
            df = SinaUSProvider().fetch_daily_bars(["SPY.US"], START, END)

        mock_call.assert_called_once_with(symbol="SPY", adjust="")
        # The out-of-range row (2026-07-09) is dropped.
        assert len(df) == 2
        row = df.iloc[-1]
        assert row["etf_code"] == "SPY.US"
        assert row["trade_date"] == date(2026, 7, 18)
        assert row["close"] == 754.0
        assert row["amount"] == 3000 * 754.0
        assert row["adj_factor"] == 1.0

    def test_single_symbol_failure_is_skipped(self):
        with (
            patch(
                "app.data.providers.sina_us_provider.ak.stock_us_daily",
                side_effect=Exception("sina unreachable"),
            ),
            patch("app.data.providers.sina_us_provider.time.sleep"),
        ):
            df = SinaUSProvider().fetch_daily_bars(["SPY.US"], START, END)
        assert df.empty
        assert list(df.columns) == [
            "etf_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "adj_factor",
        ]


# ---------------------------------------------------------------------------
# USDailyPipeline dirty-row sanitization
# ---------------------------------------------------------------------------


class TestUSDailyDirtyRows:
    def _seed_two_instruments(self, db) -> None:
        for code in ("IEX.US", "SPY.US"):
            db.add(
                ETFInfo(
                    code=code,
                    name=code,
                    market="US",
                    status="active",
                    instrument_type="ETF",
                )
            )
            db.add(
                InstrumentDailyBar(
                    etf_code=code,
                    trade_date=date(2026, 6, 30),
                    open=1,
                    high=1,
                    low=1,
                    close=1,
                )
            )
        db.commit()

    def test_drops_rows_with_open_outside_low_high(self, db_session, monkeypatch):
        """Vendor feeds (Yahoo) occasionally report an official open outside
        the daily [low, high] range; such rows must be dropped instead of
        failing L2 validation for the whole batch."""
        self._seed_two_instruments(db_session)
        monkeypatch.setattr("app.data.pipelines.us_etf.get_redis_client", _no_redis)
        pipeline = _make_pipeline(db_session)
        pipeline.provider.fetch_daily_bars.return_value = pd.DataFrame()

        good = _sina_bar("SPY.US")
        dirty = _sina_bar("IEX.US")
        dirty.loc[0, "open"] = 999.0  # open above high
        yf_df = pd.concat([good, dirty], ignore_index=True)

        with (
            patch("app.data.pipelines.us_etf.YFinanceProvider") as mock_yf,
            patch("app.data.pipelines.us_etf.SinaUSProvider") as mock_sina,
        ):
            mock_yf.return_value.fetch_daily_bars.return_value = yf_df
            mock_sina.return_value.fetch_daily_bars.return_value = pd.DataFrame()
            df = pipeline.extract()

        assert list(df["etf_code"]) == ["SPY.US"]
        assert df.iloc[0]["close"] == 754.0

    def test_drops_rows_with_high_below_low(self, db_session, monkeypatch):
        self._seed_two_instruments(db_session)
        monkeypatch.setattr("app.data.pipelines.us_etf.get_redis_client", _no_redis)
        pipeline = _make_pipeline(db_session)
        pipeline.provider.fetch_daily_bars.return_value = pd.DataFrame()

        good = _sina_bar("SPY.US")
        dirty = _sina_bar("IEX.US")
        dirty.loc[0, "high"] = 700.0  # high below low
        yf_df = pd.concat([good, dirty], ignore_index=True)

        with (
            patch("app.data.pipelines.us_etf.YFinanceProvider") as mock_yf,
            patch("app.data.pipelines.us_etf.SinaUSProvider") as mock_sina,
        ):
            mock_yf.return_value.fetch_daily_bars.return_value = yf_df
            mock_sina.return_value.fetch_daily_bars.return_value = pd.DataFrame()
            df = pipeline.extract()

        assert list(df["etf_code"]) == ["SPY.US"]


# ---------------------------------------------------------------------------
# USDailyPipeline three-source fallback chain
# ---------------------------------------------------------------------------


def _sina_bar(code: str = "SPY.US") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "etf_code": code,
                "trade_date": END,
                "open": 750.0,
                "high": 755.0,
                "low": 748.0,
                "close": 754.0,
                "volume": 3000,
                "amount": 754.0 * 3000,
                "adj_factor": 1.0,
            }
        ]
    )


class TestUSDailyFallbackChain:
    def test_sina_covers_symbols_missed_by_tiingo_and_yfinance(self, db_session, monkeypatch):
        _seed_us_instrument(db_session)
        monkeypatch.setattr("app.data.pipelines.us_etf.get_redis_client", _no_redis)
        pipeline = _make_pipeline(db_session)
        pipeline.provider.fetch_daily_bars.return_value = pd.DataFrame()

        with (
            patch("app.data.pipelines.us_etf.YFinanceProvider") as mock_yf,
            patch("app.data.pipelines.us_etf.SinaUSProvider") as mock_sina,
        ):
            mock_yf.return_value.fetch_daily_bars.return_value = pd.DataFrame()
            mock_sina.return_value.fetch_daily_bars.return_value = _sina_bar()
            df = pipeline.extract()

        assert len(df) == 1
        assert df.iloc[0]["etf_code"] == "SPY.US"
        assert df.iloc[0]["close"] == 754.0
        mock_sina.return_value.fetch_daily_bars.assert_called_once()
        # Only the symbols not covered by earlier sources are requested.
        assert mock_sina.return_value.fetch_daily_bars.call_args[0][0] == ["SPY.US"]

    def test_sina_not_called_when_yfinance_covers_all(self, db_session, monkeypatch):
        _seed_us_instrument(db_session)
        monkeypatch.setattr("app.data.pipelines.us_etf.get_redis_client", _no_redis)
        pipeline = _make_pipeline(db_session)
        pipeline.provider.fetch_daily_bars.return_value = pd.DataFrame()

        with (
            patch("app.data.pipelines.us_etf.YFinanceProvider") as mock_yf,
            patch("app.data.pipelines.us_etf.SinaUSProvider") as mock_sina,
        ):
            mock_yf.return_value.fetch_daily_bars.return_value = _sina_bar()
            df = pipeline.extract()
            mock_sina.return_value.fetch_daily_bars.assert_not_called()

        assert len(df) == 1

    def test_all_three_sources_fail_lists_each_in_error(self, db_session, monkeypatch):
        _seed_us_instrument(db_session)
        monkeypatch.setattr("app.data.pipelines.us_etf.get_redis_client", _no_redis)
        pipeline = _make_pipeline(db_session)
        pipeline.provider.fetch_daily_bars.side_effect = DataProviderError(
            "tiingo auth failed (HTTP 401)"
        )

        with (
            patch("app.data.pipelines.us_etf.YFinanceProvider") as mock_yf,
            patch("app.data.pipelines.us_etf.SinaUSProvider") as mock_sina,
        ):
            mock_yf.return_value.fetch_daily_bars.side_effect = RuntimeError("yahoo rate limited")
            mock_sina.return_value.fetch_daily_bars.side_effect = RuntimeError("sina unreachable")
            with pytest.raises(DataProviderError) as exc_info:
                pipeline.extract()

        msg = str(exc_info.value)
        assert "tiingo: tiingo auth failed (HTTP 401)" in msg
        assert "yfinance: yahoo rate limited" in msg
        assert "sina_us: sina unreachable" in msg
