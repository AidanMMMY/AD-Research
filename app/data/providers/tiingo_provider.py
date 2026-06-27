"""Tiingo data provider for US equity EOD data.

Tiingo free tier: 1,000 requests/day, 50 req/hour, 500 symbols/month,
~1 GB bandwidth/month. EOD data updated 5:30 PM EST.

Used as the primary fallback when yfinance is rate-limited or returns empty data.
API docs: https://www.tiingo.com/documentation/end-of-day
"""

import os
import time
from datetime import date, datetime, timedelta

import pandas as pd
import requests

from app.core.exceptions import DataProviderError
from app.data.providers.base import DataProvider, ETFInfo, MarketHours

# Tiingo requires a minimum 1-second delay between requests in practice,
# though the official rate limit is 50/hour.
_FREE_TIER_SAFE_DELAY = 1.5  # seconds


def _api_key() -> str:
    key = os.getenv("TIINGO_API_KEY", "")
    if not key:
        raise DataProviderError(
            "TIINGO_API_KEY environment variable is not set. "
            "Get a free key at https://www.tiingo.com/account/token"
        )
    return key


class TiingoProvider(DataProvider):
    """Tiingo data provider for US equity EOD data.

    Provides clean, adjusted historical EOD data with 30+ years history.
    Trusted by Microsoft, tastytrade, and Chainlink.
    Free tier excludes fundamentals and news, but EOD OHLCV is included.
    """

    @property
    def name(self) -> str:
        return "tiingo"

    def _to_tiingo_symbol(self, code: str) -> str:
        """Convert internal code to Tiingo symbol (plain ticker)."""
        for suffix in (".US", ".HK", ".JP"):
            if code.endswith(suffix):
                return code[: -len(suffix)]
        return code

    def fetch_etf_list(self) -> list[ETFInfo]:
        """Tiingo does not offer ETF list discovery; return empty."""
        return []

    def fetch_daily_bars(
        self, codes: list[str], start_date: date, end_date: date
    ) -> pd.DataFrame:
        """Fetch EOD OHLCV bars from Tiingo.

        Returns a DataFrame with columns:
          etf_code, trade_date, open, high, low, close, volume, amount

        Tiingo provides adjusted close prices by default (split + dividend
        adjusted). We use the unadjusted close with adjClose for reference.

        Single-code failures are logged and skipped.
        """
        rows = []
        for code in codes:
            ticker = self._to_tiingo_symbol(code)
            url = (
                f"https://api.tiingo.com/tiingo/daily/{ticker}/prices"
                f"?startDate={start_date.isoformat()}"
                f"&endDate={end_date.isoformat()}"
                f"&token={_api_key()}"
            )

            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as exc:
                print(f"[TiingoProvider] Failed to fetch {code}: {exc}")
                continue

            if not isinstance(data, list) or not data:
                continue

            for item in data:
                # Tiingo returns ISO datetimes like '2026-06-22T00:00:00.000Z'
                raw_date = item.get("date", "")
                try:
                    trade_date_val = datetime.fromisoformat(
                        raw_date.replace("Z", "+00:00")
                    ).date()
                except ValueError:
                    trade_date_val = pd.to_datetime(raw_date).date()

                close_price = float(item.get("close", 0) or 0)
                volume_val = int(item.get("volume", 0) or 0)

                rows.append(
                    {
                        "etf_code": code,
                        "trade_date": trade_date_val,
                        "open": float(item.get("open", 0) or 0),
                        "high": float(item.get("high", 0) or 0),
                        "low": float(item.get("low", 0) or 0),
                        "close": close_price,
                        "volume": volume_val,
                        "amount": volume_val * close_price,
                    }
                )

            time.sleep(_FREE_TIER_SAFE_DELAY)

        if not rows:
            return pd.DataFrame(
                columns=[
                    "etf_code", "trade_date", "open", "high", "low",
                    "close", "volume", "amount",
                ]
            )

        df = pd.DataFrame(rows)
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        return df

    def fetch_realtime_quotes(self, codes: list[str]) -> pd.DataFrame:
        """Tiingo does not provide real-time quotes on free tier.

        Returns today's EOD data instead (last available close).
        """
        today = date.today()
        start = today - timedelta(days=5)
        return self.fetch_daily_bars(codes, start, today)

    def get_market_hours(self, code: str | None = None) -> MarketHours:
        return MarketHours(
            open_time="09:30",
            close_time="16:00",
            timezone="America/New_York",
        )

    def check_health(self) -> bool:
        """Check Tiingo API is accessible."""
        try:
            url = (
                f"https://api.tiingo.com/tiingo/daily/SPY/prices"
                f"?startDate={date.today().isoformat()}"
                f"&endDate={date.today().isoformat()}"
                f"&token={_api_key()}"
            )
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            return True
        except requests.RequestException:
            return False
