"""Volatility-based strategy implementations."""

import pandas as pd

from app.data.indicators.technical import calc_atr
from app.strategies.base import ParamSpec, SignalResult, Strategy, register_strategy


@register_strategy
class ATRTrailingStopStrategy(Strategy):
    """ATR trailing stop strategy.

    Long: stop = highest close since entry - N * ATR; exit when close < stop.
    Short: stop = lowest close since entry + N * ATR; exit when close > stop.
    For signal generation we approximate using a rolling high/low trailing stop.
    """

    strategy_type = "atr_trailing_stop"
    name = "ATR吊灯止损"
    description = "沿趋势方向以ATR倍数跟踪止损线"
    family = "volatility"
    param_specs = {
        "atr_period": ParamSpec(label="ATR周期", type="int", default=14, min=5, max=60),
        "atr_multiplier": ParamSpec(
            label="ATR倍数", type="float", default=3.0, min=1.0, max=10.0
        ),
        "trend_lookback": ParamSpec(
            label="趋势回望", type="int", default=10, min=3, max=60
        ),
    }

    def bars_needed(self) -> int:
        return max(self.params["atr_period"], self.params["trend_lookback"]) + 5

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        atr_period = self.params["atr_period"]
        multiplier = self.params["atr_multiplier"]
        lookback = self.params["trend_lookback"]

        atr = calc_atr(df["high"], df["low"], df["close"], window=atr_period)
        rolling_high = df["close"].rolling(window=lookback).max()
        rolling_low = df["close"].rolling(window=lookback).min()

        prev_close = df["close"].iloc[-2]
        curr_close = df["close"].iloc[-1]
        prev_high = rolling_high.iloc[-2]
        prev_low = rolling_low.iloc[-2]
        curr_atr = atr.iloc[-1]

        if pd.isna(curr_atr) or pd.isna(prev_high) or pd.isna(prev_low):
            return None

        long_stop = prev_high - multiplier * curr_atr
        short_stop = prev_low + multiplier * curr_atr

        # Approximate: if price was above long stop and now drops below it, SELL
        if prev_close >= long_stop and curr_close < long_stop:
            return SignalResult(
                signal_type="SELL",
                strength=self._clamp_strength((long_stop - curr_close) / curr_atr * 50),
                metadata={"long_stop": round(long_stop, 4), "atr": round(curr_atr, 4)},
            )
        # If price was below short stop and now breaks above it, BUY
        if prev_close <= short_stop and curr_close > short_stop:
            return SignalResult(
                signal_type="BUY",
                strength=self._clamp_strength((curr_close - short_stop) / curr_atr * 50),
                metadata={"short_stop": round(short_stop, 4), "atr": round(curr_atr, 4)},
            )

        return SignalResult(
            signal_type="HOLD",
            strength=50,
            metadata={"long_stop": round(long_stop, 4), "short_stop": round(short_stop, 4)},
        )

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        atr_period = self.params["atr_period"]
        multiplier = self.params["atr_multiplier"]
        lookback = self.params["trend_lookback"]

        atr = calc_atr(df["high"], df["low"], df["close"], window=atr_period)
        rolling_high = df["close"].rolling(window=lookback).max()
        rolling_low = df["close"].rolling(window=lookback).min()

        long_stop = rolling_high - multiplier * atr
        short_stop = rolling_low + multiplier * atr

        signals = pd.Series(0, index=df.index)
        signals[(df["close"].shift(1) >= long_stop.shift(1)) & (df["close"] < long_stop)] = -1
        signals[(df["close"].shift(1) <= short_stop.shift(1)) & (df["close"] > short_stop)] = 1
        return signals


@register_strategy
class VolatilityBreakoutStrategy(Strategy):
    """Volatility breakout strategy.

    BUY when the close breaks above previous close + K * ATR.
    SELL when the close breaks below previous close - K * ATR.
    """

    strategy_type = "volatility_breakout"
    name = "波动率突破"
    description = "收盘价突破前收盘±K×ATR买入/卖出"
    family = "volatility"
    param_specs = {
        "atr_period": ParamSpec(label="ATR周期", type="int", default=14, min=5, max=60),
        "breakout_multiplier": ParamSpec(
            label="突破倍数", type="float", default=1.5, min=0.5, max=5.0
        ),
    }

    def bars_needed(self) -> int:
        return self.params["atr_period"] + 5

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        atr_period = self.params["atr_period"]
        multiplier = self.params["breakout_multiplier"]

        atr = calc_atr(df["high"], df["low"], df["close"], window=atr_period)
        prev_close = df["close"].iloc[-2]
        curr_close = df["close"].iloc[-1]
        curr_atr = atr.iloc[-1]

        if pd.isna(curr_atr):
            return None

        upper = prev_close + multiplier * curr_atr
        lower = prev_close - multiplier * curr_atr

        if curr_close > upper:
            return SignalResult(
                signal_type="BUY",
                strength=self._clamp_strength((curr_close - upper) / curr_atr * 100),
                metadata={"upper": round(upper, 4), "lower": round(lower, 4)},
            )
        if curr_close < lower:
            return SignalResult(
                signal_type="SELL",
                strength=self._clamp_strength((lower - curr_close) / curr_atr * 100),
                metadata={"upper": round(upper, 4), "lower": round(lower, 4)},
            )

        return SignalResult(
            signal_type="HOLD",
            strength=50,
            metadata={"upper": round(upper, 4), "lower": round(lower, 4)},
        )

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        atr_period = self.params["atr_period"]
        multiplier = self.params["breakout_multiplier"]

        atr = calc_atr(df["high"], df["low"], df["close"], window=atr_period)
        upper = df["close"].shift(1) + multiplier * atr
        lower = df["close"].shift(1) - multiplier * atr

        signals = pd.Series(0, index=df.index)
        signals[df["close"] > upper] = 1
        signals[df["close"] < lower] = -1
        return signals
