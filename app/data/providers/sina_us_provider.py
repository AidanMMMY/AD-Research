"""Sina Finance US equity daily provider (via akshare).

Last-resort fallback for US daily bars when both Tiingo and yfinance fail.
akshare's ``stock_us_daily`` hits Sina's static data endpoint; its values
have been verified to match the bars already stored in the database, and it
requires no API key, so it stays usable from cloud IPs where Yahoo is
rate-limited.
"""

import logging
import socket
import time
from datetime import date

import akshare as ak
import pandas as pd

from app.data.providers.base import DataProvider, ETFInfo, MarketHours

logger = logging.getLogger(__name__)

# akshare issues plain requests.get() calls without a timeout; cap the
# blocking time so a hung Sina connection cannot stall the whole ETL run.
_SOCKET_TIMEOUT = 30

# Delay between symbols: Sina serves two requests per symbol (prices +
# adjustment factors) and throttles aggressive clients.
_SAFE_DELAY = 0.5

_EMPTY_COLUMNS = [
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


class SinaUSProvider(DataProvider):
    """Sina Finance US equity EOD provider.

    Returns raw (unadjusted) OHLCV bars. Sina does not expose a reliable
    per-day adjustment factor (its qfq-factor table is known to be wrong
    for some symbols), so ``adj_factor`` is set to 1.0. This matches the
    Tiingo convention (adjClose/close) for the latest bars, where no
    split/dividend has happened since.
    """

    @property
    def name(self) -> str:
        return "sina_us"

    def _to_sina_symbol(self, code: str) -> str:
        """Convert internal code to Sina symbol (plain uppercase ticker)."""
        for suffix in (".US", ".HK", ".JP"):
            if code.endswith(suffix):
                return code[: -len(suffix)]
        return code

    def fetch_etf_list(self) -> list[ETFInfo]:
        """Sina does not offer instrument discovery; return empty."""
        return []

    def fetch_daily_bars(self, codes: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        """Fetch daily OHLCV bars from Sina via akshare.

        Returns a DataFrame with columns:
          etf_code, trade_date, open, high, low, close, volume, amount, adj_factor

        ``stock_us_daily`` always returns the full listing history, so rows
        are filtered to [start_date, end_date] after the fetch. Single-code
        failures are logged and skipped so one bad symbol never aborts the
        batch.
        """
        rows = []
        for code in codes:
            symbol = self._to_sina_symbol(code)
            try:
                previous_timeout = socket.getdefaulttimeout()
                socket.setdefaulttimeout(_SOCKET_TIMEOUT)
                try:
                    df = ak.stock_us_daily(symbol=symbol, adjust="")
                finally:
                    socket.setdefaulttimeout(previous_timeout)
            except Exception as exc:
                logger.warning(
                    "[SinaUSProvider] Failed to fetch %s (%s): %s",
                    code,
                    symbol,
                    exc,
                )
                continue

            if df is None or df.empty:
                logger.warning("[SinaUSProvider] No data for %s (%s)", code, symbol)
                continue

            df = df.copy()
            df["date"] = pd.to_datetime(df["date"]).dt.date
            df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]

            for _, row in df.iterrows():
                close_price = float(row["close"])
                volume_val = int(row["volume"])
                rows.append(
                    {
                        "etf_code": code,
                        "trade_date": row["date"],
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": close_price,
                        "volume": volume_val,
                        "amount": volume_val * close_price,
                        "adj_factor": 1.0,
                    }
                )

            time.sleep(_SAFE_DELAY)

        if not rows:
            logger.warning(
                "[SinaUSProvider] No rows returned for %d requested codes",
                len(codes),
            )
            return pd.DataFrame(columns=_EMPTY_COLUMNS)

        return pd.DataFrame(rows)

    def fetch_realtime_quotes(self, codes: list[str]) -> pd.DataFrame:
        """Sina US endpoint is EOD-only; return recent daily bars instead."""
        today = date.today()
        from datetime import timedelta

        start = today - timedelta(days=5)
        return self.fetch_daily_bars(codes, start, today)

    def get_market_hours(self, code: str | None = None) -> MarketHours:
        return MarketHours(
            open_time="09:30",
            close_time="16:00",
            timezone="America/New_York",
        )

    def check_health(self) -> bool:
        """Check the Sina US endpoint is accessible via a SPY fetch."""
        try:
            df = ak.stock_us_daily(symbol="SPY", adjust="")
            return df is not None and not df.empty
        except Exception:
            return False
