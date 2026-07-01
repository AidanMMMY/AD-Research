"""Trend-following strategy implementations."""

import pandas as pd

from app.data.indicators.technical import calc_ma, calc_macd
from app.strategies.base import ParamSpec, SignalResult, Strategy, register_strategy


@register_strategy
class MACrossoverStrategy(Strategy):
    """Moving average crossover strategy.

    BUY when the short-term MA crosses above the long-term MA.
    SELL when the short-term MA crosses below the long-term MA.
    """

    strategy_type = "ma_crossover"
    name = "均线交叉"
    description = "短期均线上穿长期均线买入，下穿卖出"
    family = "trend_following"
    param_specs = {
        "short_window": ParamSpec(
            label="短期窗口",
            type="int",
            default=10,
            min=3,
            max=60,
            description="短期移动平均线窗口",
        ),
        "long_window": ParamSpec(
            label="长期窗口",
            type="int",
            default=30,
            min=10,
            max=252,
            description="长期移动平均线窗口",
        ),
    }

    def bars_needed(self) -> int:
        return self.params["long_window"] + 5

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        short_window = self.params["short_window"]
        long_window = self.params["long_window"]

        short_ma = calc_ma(df["close"], short_window)
        long_ma = calc_ma(df["close"], long_window)

        prev_short = short_ma.iloc[-2]
        prev_long = long_ma.iloc[-2]
        curr_short = short_ma.iloc[-1]
        curr_long = long_ma.iloc[-1]

        if pd.isna(prev_short) or pd.isna(prev_long):
            return None

        prev_diff = prev_short - prev_long
        curr_diff = curr_short - curr_long

        if prev_diff <= 0 < curr_diff:
            strength = self._clamp_strength(abs(curr_diff) / curr_long * 1000)
            return SignalResult(
                signal_type="BUY",
                strength=strength,
                metadata={
                    "short_ma": round(curr_short, 4),
                    "long_ma": round(curr_long, 4),
                },
            )
        if prev_diff >= 0 > curr_diff:
            strength = self._clamp_strength(abs(curr_diff) / curr_long * 1000)
            return SignalResult(
                signal_type="SELL",
                strength=strength,
                metadata={
                    "short_ma": round(curr_short, 4),
                    "long_ma": round(curr_long, 4),
                },
            )

        return SignalResult(signal_type="HOLD", strength=50)

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        short_window = self.params["short_window"]
        long_window = self.params["long_window"]

        short_ma = calc_ma(df["close"], short_window)
        long_ma = calc_ma(df["close"], long_window)

        signals = pd.Series(0, index=df.index)
        signals[(short_ma.shift(1) <= long_ma.shift(1)) & (short_ma > long_ma)] = 1
        signals[(short_ma.shift(1) >= long_ma.shift(1)) & (short_ma < long_ma)] = -1
        return signals


@register_strategy
class MACDStrategy(Strategy):
    """MACD signal strategy.

    BUY when the MACD histogram turns positive (DIF crosses above DEA).
    SELL when the histogram turns negative.
    """

    strategy_type = "macd_signal"
    name = "MACD信号"
    description = "MACD柱状线由负转正买入，由正转负卖出"
    family = "trend_following"
    param_specs = {
        "fast": ParamSpec(label="快线", type="int", default=12, min=2, max=60),
        "slow": ParamSpec(label="慢线", type="int", default=26, min=5, max=120),
        "signal": ParamSpec(label="信号线", type="int", default=9, min=2, max=60),
    }

    def bars_needed(self) -> int:
        return self.params["slow"] + self.params["signal"] + 5

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        fast = self.params["fast"]
        slow = self.params["slow"]
        signal_window = self.params["signal"]

        dif, dea, hist = calc_macd(df["close"], fast=fast, slow=slow, signal=signal_window)

        prev_hist = hist.iloc[-2]
        curr_hist = hist.iloc[-1]

        if pd.isna(prev_hist):
            return None

        if prev_hist <= 0 < curr_hist:
            return SignalResult(
                signal_type="BUY",
                strength=self._clamp_strength(abs(curr_hist) * 100),
                metadata={"dif": round(dif.iloc[-1], 4), "dea": round(dea.iloc[-1], 4)},
            )
        if prev_hist >= 0 > curr_hist:
            return SignalResult(
                signal_type="SELL",
                strength=self._clamp_strength(abs(curr_hist) * 100),
                metadata={"dif": round(dif.iloc[-1], 4), "dea": round(dea.iloc[-1], 4)},
            )

        return SignalResult(signal_type="HOLD", strength=50)

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        fast = self.params["fast"]
        slow = self.params["slow"]
        signal_window = self.params["signal"]

        _, _, hist = calc_macd(df["close"], fast=fast, slow=slow, signal=signal_window)
        signals = pd.Series(0, index=df.index)
        signals[(hist.shift(1) <= 0) & (hist > 0)] = 1
        signals[(hist.shift(1) >= 0) & (hist < 0)] = -1
        return signals


@register_strategy
class DonchianBreakoutStrategy(Strategy):
    """Donchian channel breakout strategy.

    BUY when the close breaks above the highest high of the lookback period.
    SELL when the close breaks below the lowest low of the lookback period.
    """

    strategy_type = "donchian_breakout"
    name = "唐奇安通道突破"
    description = "收盘价突破N日高点买入，跌破N日低点卖出"
    family = "trend_following"
    param_specs = {
        "channel_period": ParamSpec(
            label="通道周期",
            type="int",
            default=20,
            min=5,
            max=60,
        ),
    }

    def bars_needed(self) -> int:
        return self.params["channel_period"] + 5

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        period = self.params["channel_period"]

        upper = df["high"].rolling(window=period).max()
        lower = df["low"].rolling(window=period).min()

        prev_close = df["close"].iloc[-2]
        curr_close = df["close"].iloc[-1]
        prev_upper = upper.iloc[-2]
        curr_upper = upper.iloc[-1]
        prev_lower = lower.iloc[-2]
        curr_lower = lower.iloc[-1]

        if pd.isna(prev_upper) or pd.isna(prev_lower):
            return None

        if prev_close <= prev_upper < curr_close:
            return SignalResult(
                signal_type="BUY",
                strength=self._clamp_strength(
                    (curr_close - curr_upper) / curr_upper * 500
                ),
                metadata={"upper": round(curr_upper, 4), "lower": round(curr_lower, 4)},
            )
        if prev_close >= prev_lower > curr_close:
            return SignalResult(
                signal_type="SELL",
                strength=self._clamp_strength(
                    (curr_lower - curr_close) / curr_close * 500
                ),
                metadata={"upper": round(curr_upper, 4), "lower": round(curr_lower, 4)},
            )

        return SignalResult(signal_type="HOLD", strength=50)

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        period = self.params["channel_period"]

        upper = df["high"].rolling(window=period).max()
        lower = df["low"].rolling(window=period).min()

        signals = pd.Series(0, index=df.index)
        signals[(df["close"].shift(1) <= upper.shift(1)) & (df["close"] > upper)] = 1
        signals[(df["close"].shift(1) >= lower.shift(1)) & (df["close"] < lower)] = -1
        return signals
