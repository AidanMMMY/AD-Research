"""Signal generation engine.

Generates BUY/SELL/HOLD signals based on strategy configurations.
"""

from datetime import date
from typing import Any, Dict, List

import pandas as pd

from app.data.providers.akshare_provider import AkshareProvider


def generate_signals_for_strategy(
    etf_code: str,
    strategy_type: str,
    params: Dict[str, Any],
    trade_date: date,
    lookback_days: int = 60,
) -> List[Dict[str, Any]]:
    """Generate signals for a single strategy on a single ETF.

    Args:
        etf_code: ETF code.
        strategy_type: Type of strategy.
        params: Strategy parameters.
        trade_date: Date to generate signals for.
        lookback_days: Number of days to fetch for calculation.

    Returns:
        List of signal dicts with type and strength.
    """
    # Fetch historical data
    try:
        provider = AkshareProvider()
        start = trade_date - pd.Timedelta(days=lookback_days)
        df = provider.fetch_daily_bars([etf_code], start, trade_date)
    except Exception:
        return []

    if df.empty or len(df) < 30:
        return []

    df = df.sort_values("trade_date").reset_index(drop=True)

    # Get latest data point
    latest = df.iloc[-1]
    latest_date = pd.to_datetime(latest["trade_date"]).date()

    if latest_date != trade_date:
        return []

    signals = []

    if strategy_type == "momentum":
        window = params.get("momentum_window", 20)
        threshold = params.get("threshold", 0.05)
        if len(df) >= window + 1:
            momentum = (latest["close"] - df.iloc[-window - 1]["close"]) / df.iloc[-window - 1]["close"]
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
            closes = df["close"].values
            deltas = pd.Series(closes).diff().dropna()
            gains = deltas.where(deltas > 0, 0).rolling(period).mean().iloc[-1]
            losses = (-deltas.where(deltas < 0, 0)).rolling(period).mean().iloc[-1]
            if losses > 0:
                rs = gains / losses
                rsi = 100 - 100 / (1 + rs)
                if rsi < oversold:
                    signals.append({"type": "BUY", "strength": min(int((oversold - rsi) * 3), 100)})
                elif rsi > overbought:
                    signals.append({"type": "SELL", "strength": min(int((rsi - overbought) * 3), 100)})
                else:
                    signals.append({"type": "HOLD", "strength": 50})

    return signals
