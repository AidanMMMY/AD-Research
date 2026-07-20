"""Tiingo data provider for US equity EOD data.

Tiingo free tier: 1,000 requests/day, 50 req/hour, 500 symbols/month,
~1 GB bandwidth/month. EOD data updated 5:30 PM EST.

Used as the primary fallback when yfinance is rate-limited or returns empty data.
API docs: https://www.tiingo.com/documentation/end-of-day
"""

import logging
import os
import re
import time
from datetime import date, datetime, timedelta

import pandas as pd
import requests

from app.core.exceptions import DataProviderError
from app.data.providers.base import DataProvider, ETFInfo, MarketHours

logger = logging.getLogger(__name__)

# Tiingo requires a minimum 1-second delay between requests in practice,
# though the official rate limit is 50/hour.
_FREE_TIER_SAFE_DELAY = 1.5  # seconds

# Abort the batch after this many consecutive HTTP 429 responses: the
# hourly quota is exhausted and hammering the remaining symbols only
# burns the daily/monthly quota for nothing.
_MAX_CONSECUTIVE_RATE_LIMITS = 3


def _redact_api_key(message: object) -> str:
    """Mask API-key query params in URLs embedded in error messages.

    ``requests`` exceptions include the full request URL (e.g. urllib3
    connection errors and ``HTTPError`` from ``raise_for_status``), and the
    Tiingo key travels as a ``token=`` query param — never log it raw.
    """
    return re.sub(r"(?i)(token|apikey|api_key)=[^&\s]+", r"\1=***", str(message))


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
          etf_code, trade_date, open, high, low, close, volume, amount, adj_factor

        Tiingo provides adjusted close prices via adjClose. We store the raw
        close and set adj_factor = adjClose / close so consumers can compute
        split/dividend adjusted prices as close * adj_factor.

        Single-code failures are logged with the HTTP status and skipped.
        Auth failures (401/403) raise immediately since no request in the
        batch can succeed; repeated 429s abort the batch early so the
        caller can fall back to another source.
        """
        rows = []
        failed = 0
        consecutive_rate_limits = 0
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
            except requests.RequestException as exc:
                failed += 1
                logger.warning(
                    "[TiingoProvider] Request failed for %s (%s): %s",
                    code, ticker, _redact_api_key(exc),
                )
                continue

            if resp.status_code in (401, 403):
                raise DataProviderError(
                    f"tiingo auth failed (HTTP {resp.status_code}) for {ticker}: "
                    f"{resp.text[:200]} — check TIINGO_API_KEY"
                )
            if resp.status_code == 429:
                failed += 1
                consecutive_rate_limits += 1
                logger.warning(
                    "[TiingoProvider] Rate limited (HTTP 429) for %s (%s): %s",
                    code, ticker, resp.text[:200],
                )
                if consecutive_rate_limits >= _MAX_CONSECUTIVE_RATE_LIMITS:
                    logger.warning(
                        "[TiingoProvider] Aborting batch after %d consecutive "
                        "429 responses (hourly quota likely exhausted)",
                        consecutive_rate_limits,
                    )
                    break
                continue
            consecutive_rate_limits = 0

            try:
                resp.raise_for_status()
                data = resp.json()
            except (requests.RequestException, ValueError) as exc:
                failed += 1
                logger.warning(
                    "[TiingoProvider] Failed to fetch %s (%s), HTTP %s: %s",
                    code, ticker, resp.status_code, _redact_api_key(exc),
                )
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
                adj_close = float(item.get("adjClose", close_price) or close_price)
                adj_factor = adj_close / close_price if close_price else 1.0
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
                        "adj_factor": adj_factor,
                    }
                )

            time.sleep(_FREE_TIER_SAFE_DELAY)

        if not rows:
            logger.warning(
                "[TiingoProvider] No rows returned for %d/%d requested codes",
                len(codes) - failed, len(codes),
            )
            return pd.DataFrame(
                columns=[
                    "etf_code", "trade_date", "open", "high", "low",
                    "close", "volume", "amount", "adj_factor",
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
