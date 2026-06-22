from datetime import date

import pandas as pd
import yfinance as yf

from app.core.exceptions import DataProviderError
from app.data.providers.base import DataProvider, ETFInfo, MarketHours


class YFinanceProvider(DataProvider):
    """Yahoo Finance data provider for cross-border ETFs."""

    # Hard-coded ticker mappings for common ETFs
    CODE_MAP = {
        "SPY.US": "SPY",
        "QQQ.US": "QQQ",
        "IWM.US": "IWM",
        "EFA.US": "EFA",
        "EEM.US": "EEM",
        "VTI.US": "VTI",
        "VXUS.US": "VXUS",
        "BND.US": "BND",
        "GLD.US": "GLD",
        "TLT.US": "TLT",
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
        """Convert internal ETF code to yfinance ticker symbol.

        Supports CODE_MAP hard-coded mappings.
        Default rules:
          - .US suffix is stripped
          - .JP suffix becomes .T
          - .HK suffix is kept as-is
        """
        if code in self.CODE_MAP:
            return self.CODE_MAP[code]

        if code.endswith(".US"):
            return code[:-3]
        if code.endswith(".JP"):
            return code[:-3] + ".T"
        if code.endswith(".HK"):
            return code

        # Fallback: return as-is
        return code

    def fetch_etf_list(self) -> list[ETFInfo]:
        """yfinance does not provide a list interface; return empty list."""
        return []

    def fetch_daily_bars(
        self, codes: list[str], start_date: date, end_date: date
    ) -> pd.DataFrame:
        """Fetch daily OHLCV bars for the given ETF codes.

        Returns a DataFrame with columns:
          etf_code, trade_date, open, high, low, close, volume, amount

        amount is estimated as volume * close (yfinance does not provide amount).
        Single-code failures are logged and skipped so other codes still return data.
        """
        rows = []
        for code in codes:
            ticker = self._to_ticker(code)
            try:
                hist = yf.Ticker(ticker).history(
                    start=start_date, end=end_date
                )
            except Exception as exc:
                # Log and continue so one bad ticker does not break the batch.
                print(f"[YFinanceProvider] Failed to fetch {code} ({ticker}): {exc}")
                continue

            if hist.empty:
                continue

            for trade_date, row in hist.iterrows():
                trade_date = (
                    trade_date.date()
                    if hasattr(trade_date, "date")
                    else trade_date
                )
                volume = int(row.get("Volume", 0))
                close_price = float(row.get("Close", 0))
                rows.append(
                    {
                        "etf_code": code,
                        "trade_date": trade_date,
                        "open": float(row.get("Open", 0)),
                        "high": float(row.get("High", 0)),
                        "low": float(row.get("Low", 0)),
                        "close": close_price,
                        "volume": volume,
                        "amount": volume * close_price,
                    }
                )

        if not rows:
            return pd.DataFrame(
                columns=[
                    "etf_code",
                    "trade_date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "amount",
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

        # yf.download returns a MultiIndex DataFrame when multiple tickers
        # are requested; normalise to a flat DataFrame.
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
        """Return market hours for the given ETF code.

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

            for trade_date, row in hist.iterrows():
                trade_date = (
                    trade_date.date()
                    if hasattr(trade_date, "date")
                    else trade_date
                )
                rows.append(
                    {
                        "pair": pair,
                        "trade_date": trade_date,
                        "rate": float(row.get("Close", 0)),
                    }
                )

        if not rows:
            return pd.DataFrame(columns=["pair", "trade_date", "rate"])

        df = pd.DataFrame(rows)
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        return df
