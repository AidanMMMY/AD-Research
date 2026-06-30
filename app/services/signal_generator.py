"""Signal generation engine.

Generates BUY/SELL/HOLD signals based on strategy configurations.
Reads historical data from the local instrument_daily_bar table instead of
making external API calls.
"""

from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.data.indicators.technical import calc_rsi
from app.data.repositories import price_repository

# Extra calendar days added to the requested ``lookback_days`` when fetching
# bars, to absorb weekends, public holidays, and exchange closures.  Sized to
# comfortably cover a 7-day window plus a multi-day holiday stretch.
LOOKBACK_BUFFER = 30


def _fetch_bars_from_db(
    db: Session,
    etf_code: str,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Fetch adjusted daily bars from the local price repository.

    Returns:
        DataFrame with columns: etf_code, trade_date, open, high, low,
        close, adj_close, volume. Empty DataFrame if no data.
    """
    if price_repository.is_before_list_date(db, etf_code, end_date):
        return pd.DataFrame()

    df = price_repository.get_bars(
        db, etf_code, start_date, end_date, adjusted=True
    )
    if df.empty:
        return df

    df = df.rename(columns={"close": "raw_close", "adj_close": "close"})
    df["etf_code"] = etf_code
    return df[["etf_code", "trade_date", "open", "high", "low", "close", "volume"]]


def generate_signals_for_strategy(
    db: Session,
    etf_code: str,
    strategy_type: str,
    params: dict[str, Any],
    trade_date: date,
    lookback_days: int = 60,
) -> list[dict[str, Any]]:
    """Generate signals for a single strategy on a single ETF.

    Args:
        db: SQLAlchemy session for reading local daily bars.
        etf_code: ETF code.
        strategy_type: Type of strategy.
        params: Strategy parameters.
        trade_date: Date to generate signals for. Uses the latest
            available bar on or before this date if exact date is missing.
        lookback_days: Number of days to fetch for calculation.

    Returns:
        List of signal dicts with type and strength.
    """
    start = trade_date - pd.Timedelta(days=lookback_days + LOOKBACK_BUFFER)
    df = _fetch_bars_from_db(db, etf_code, start, trade_date)

    if df.empty or len(df) < 30:
        return []

    # Convert Decimal columns to float for pandas arithmetic
    numeric_cols = ["open", "high", "low", "close", "volume"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("trade_date").reset_index(drop=True)

    # Use the latest available bar (may differ from trade_date on weekends/holidays)
    latest = df.iloc[-1]

    signals = []

    if strategy_type == "momentum":
        window = params.get("momentum_window", 20)
        threshold = params.get("threshold", 0.05)
        if len(df) >= window + 1:
            prev_close = df.iloc[-window - 1]["close"]
            if prev_close == 0 or pd.isna(prev_close):
                return signals
            momentum = (latest["close"] - prev_close) / prev_close
            if momentum > threshold:
                signals.append({"type": "BUY", "strength": min(int(momentum * 100), 100)})
            elif momentum < -threshold:
                signals.append({"type": "SELL", "strength": min(int(abs(momentum) * 100), 100)})
            else:
                signals.append({"type": "HOLD", "strength": 50})

    elif strategy_type == "mean_reversion":
        window = params.get("lookback_window", 20)
        z_threshold = params.get("z_score_threshold", 2.0)
        if len(df) >= window:
            recent = df.tail(window)
            mean = recent["close"].mean()
            std = recent["close"].std()
            if std > 0:
                z_score = (latest["close"] - mean) / std
                if z_score < -z_threshold:
                    signals.append({"type": "BUY", "strength": min(int(abs(z_score) * 30), 100)})
                elif z_score > z_threshold:
                    signals.append({"type": "SELL", "strength": min(int(z_score * 30), 100)})
                else:
                    signals.append({"type": "HOLD", "strength": 50})

    elif strategy_type == "rsi":
        period = params.get("rsi_period", 14)
        overbought = params.get("overbought", 70)
        oversold = params.get("oversold", 30)
        if len(df) >= period + 1:
            rsi = calc_rsi(df["close"], window=period).iloc[-1]
            if pd.isna(rsi):
                signals.append({"type": "HOLD", "strength": 50})
            elif rsi < oversold:
                signals.append({"type": "BUY", "strength": min(int((oversold - rsi) * 3), 100)})
            elif rsi > overbought:
                signals.append({"type": "SELL", "strength": min(int((rsi - overbought) * 3), 100)})
            else:
                signals.append({"type": "HOLD", "strength": 50})

    return signals
