"""Yahoo Finance data provider for cross-border and US equities.

Primary data source for US ETF and individual stock daily bars.
Uses the unofficial yfinance library (no API key required).

Rate limits: ~2,000 requests/hour for unofficial endpoints.
Requests are throttled with 2-second delays between individual calls.
Batch download via yf.download() is more efficient for multi-ticker pulls.
"""

import time
from datetime import date

import pandas as pd
import yfinance as yf

from app.core.exceptions import DataProviderError
from app.data.providers.base import DataProvider, ETFInfo, MarketHours

# Safe rate limit for yfinance: 1 request per 2 seconds
_SAFE_DELAY = 2.0
# Maximum tickers per batch download via yf.download()
_MAX_BATCH_SIZE = 20


class YFinanceProvider(DataProvider):
    """Yahoo Finance data provider for cross-border and US equities.

    Provides daily OHLCV bars, financial statements, and key statistics
    via the unofficial yfinance library. No API key required.

    Primary for: US ETF & stock EOD batch downloads.
    Reliability: breaks 2-4x/year when Yahoo changes HTML structure.
    Always pair with TiingoProvider or FinnhubProvider as fallback.
    """

    # Hard-coded ticker mappings for non-standard tickers.
    # The default suffix-based mapping (see _to_ticker) handles most
    # cases automatically — US tickers strip .US, HK stays as-is.
    CODE_MAP: dict[str, str] = {
        "1321.JP": "1321.T",
        "1306.JP": "1306.T",
        "2800.HK": "2800.HK",
        "2822.HK": "2822.HK",
        "3188.HK": "3188.HK",
    }

    @property
    def name(self) -> str:
        return "yfinance"

    def _to_ticker(self, code: str) -> str:
        """Convert internal instrument code to yfinance ticker symbol.

        Mapping rules (in priority order):
          1. Exact match in CODE_MAP (for non-standard tickers)
          2. .US suffix → strip (e.g. SPY.US → SPY)
          3. .JP suffix → .T   (e.g. 1321.JP → 1321.T)
          4. .HK suffix → keep (e.g. 2800.HK → 2800.HK)
          5. Fallback: return as-is
        """
        if code in self.CODE_MAP:
            return self.CODE_MAP[code]

        if code.endswith(".US"):
            return code[:-3]
        if code.endswith(".JP"):
            return code[:-3] + ".T"
        if code.endswith(".HK"):
            return code

        return code

    def fetch_etf_list(self) -> list[ETFInfo]:
        """yfinance does not provide an ETF list API; return empty."""
        return []

    def fetch_daily_bars(
        self, codes: list[str], start_date: date, end_date: date
    ) -> pd.DataFrame:
        """Fetch daily OHLCV bars for the given instrument codes.

        Uses batch yf.download() for efficiency when possible (up to
        _MAX_BATCH_SIZE tickers per call). Falls back to single-ticker
        fetch for failures.

        Returns a DataFrame with columns:
          etf_code, trade_date, open, high, low, close, volume, amount

        amount is estimated as volume * close (yfinance does not provide
        turnover amount separately).
        """
        if not codes:
            return pd.DataFrame(
                columns=[
                    "etf_code", "trade_date", "open", "high", "low",
                    "close", "volume", "amount",
                ]
            )

        rows = []

        # Batch download for efficiency: split into chunks of _MAX_BATCH_SIZE
        for i in range(0, len(codes), _MAX_BATCH_SIZE):
            chunk_codes = codes[i : i + _MAX_BATCH_SIZE]
            tickers = [self._to_ticker(c) for c in chunk_codes]
            ticker_str = " ".join(tickers)

            batch_success = False
            try:
                data = yf.download(
                    tickers=ticker_str,
                    start=start_date,
                    end=end_date,
                    progress=False,
                    auto_adjust=False,
                )
                batch_success = not data.empty
            except Exception as exc:
                print(
                    f"[YFinanceProvider] Batch download failed for "
                    f"{len(chunk_codes)} tickers: {exc}. Falling back to single-ticker."
                )

            if batch_success:
                # Parse batch result: MultiIndex columns when >1 ticker
                for code, ticker in zip(chunk_codes, tickers, strict=False):
                    try:
                        if len(tickers) == 1:
                            series = data
                        else:
                            series = data.xs(ticker, level=1, axis=1)
                        for trade_date_val, row in series.iterrows():
                            td = (
                                trade_date_val.date()
                                if hasattr(trade_date_val, "date")
                                else trade_date_val
                            )
                            close_price = float(row.get("Close", 0) or 0)
                            volume_val = int(row.get("Volume", 0) or 0)
                            rows.append(
                                {
                                    "etf_code": code,
                                    "trade_date": td,
                                    "open": float(row.get("Open", 0) or 0),
                                    "high": float(row.get("High", 0) or 0),
                                    "low": float(row.get("Low", 0) or 0),
                                    "close": close_price,
                                    "volume": volume_val,
                                    "amount": volume_val * close_price,
                                }
                            )
                    except Exception:
                        continue
            else:
                # Fallback: single-ticker fetch
                for code in chunk_codes:
                    ticker = self._to_ticker(code)
                    try:
                        hist = yf.Ticker(ticker).history(
                            start=start_date, end=end_date
                        )
                    except Exception as exc:
                        print(
                            f"[YFinanceProvider] Failed to fetch {code} "
                            f"({ticker}): {exc}"
                        )
                        continue

                    if hist.empty:
                        continue

                    for trade_date_val, row in hist.iterrows():
                        td = (
                            trade_date_val.date()
                            if hasattr(trade_date_val, "date")
                            else trade_date_val
                        )
                        close_price = float(row.get("Close", 0) or 0)
                        volume_val = int(row.get("Volume", 0) or 0)
                        rows.append(
                            {
                                "etf_code": code,
                                "trade_date": td,
                                "open": float(row.get("Open", 0) or 0),
                                "high": float(row.get("High", 0) or 0),
                                "low": float(row.get("Low", 0) or 0),
                                "close": close_price,
                                "volume": volume_val,
                                "amount": volume_val * close_price,
                            }
                        )

            # Rate limiting between batches
            time.sleep(_SAFE_DELAY)

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
        """Fetch latest quotes using yf.download().

        Raises DataProviderError on failure.
        """
        tickers = [self._to_ticker(c) for c in codes]
        try:
            data = yf.download(
                tickers=" ".join(tickers),
                period="1d",
                interval="1d",
                progress=False,
            )
        except Exception as exc:
            raise DataProviderError(
                f"yfinance realtime fetch failed: {exc}"
            ) from exc

        if data.empty:
            raise DataProviderError(
                "yfinance returned empty data for realtime quotes"
            )

        rows = []
        for code, ticker in zip(codes, tickers, strict=False):
            try:
                if len(tickers) == 1:
                    row = data.iloc[-1]
                else:
                    row = data.xs(ticker, level=1, axis=1).iloc[-1]
                rows.append(
                    {
                        "etf_code": code,
                        "price": float(row.get("Close", 0)),
                        "volume": int(row.get("Volume", 0)),
                        "open": float(row.get("Open", 0)),
                        "high": float(row.get("High", 0)),
                        "low": float(row.get("Low", 0)),
                    }
                )
            except Exception:
                continue

        return pd.DataFrame(rows)

    def get_market_hours(self, code: str | None = None) -> MarketHours:
        """Return market hours for the given instrument code.

        Infers the market from the code suffix:
          - .US -> US (NYSE/NASDAQ) 09:30-16:00 America/New_York
          - .HK -> Hong Kong 09:30-16:00 Asia/Hong_Kong
          - .JP -> Japan 09:00-15:00 Asia/Tokyo
          - default -> US
        """
        if code and code.endswith(".HK"):
            return MarketHours(
                open_time="09:30",
                close_time="16:00",
                timezone="Asia/Hong_Kong",
            )
        if code and code.endswith(".JP"):
            return MarketHours(
                open_time="09:00",
                close_time="15:00",
                timezone="Asia/Tokyo",
            )
        return MarketHours(
            open_time="09:30",
            close_time="16:00",
            timezone="America/New_York",
        )

    def fetch_fx_rates(
        self, pairs: list[str], start_date: date, end_date: date
    ) -> pd.DataFrame:
        """Fetch FX rates (e.g. USDCNY=X, HKDCNY=X, JPYCNY=X).

        Returns a DataFrame with columns: pair, trade_date, rate.
        """
        rows = []
        for pair in pairs:
            try:
                hist = yf.Ticker(pair).history(
                    start=start_date, end=end_date
                )
            except Exception as exc:
                print(f"[YFinanceProvider] Failed to fetch FX {pair}: {exc}")
                continue

            if hist.empty:
                continue

            for trade_date_val, row in hist.iterrows():
                td = (
                    trade_date_val.date()
                    if hasattr(trade_date_val, "date")
                    else trade_date_val
                )
                rows.append(
                    {
                        "pair": pair,
                        "trade_date": td,
                        "rate": float(row.get("Close", 0)),
                    }
                )

        if not rows:
            return pd.DataFrame(columns=["pair", "trade_date", "rate"])

        df = pd.DataFrame(rows)
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        return df
