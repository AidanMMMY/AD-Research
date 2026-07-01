"""Composite / multi-factor strategy implementations."""

import pandas as pd

from app.data.indicators.technical import calc_ma, calc_rsi
from app.strategies.base import ParamSpec, SignalResult, Strategy, register_strategy


@register_strategy
class TripleScreenStrategy(Strategy):
    """Triple screen strategy.

    Combines trend (MA slope), momentum (RSI), and volume (volume spike)
    into a 0-3 score. BUY when the score reaches the threshold, SELL when
    the score is at or below (3 - threshold).
    """

    strategy_type = "triple_screen"
    name = "三重滤网"
    description = "趋势+RSI+成交量三重打分复合策略"
    family = "composite"
    param_specs = {
        "trend_window": ParamSpec(
            label="趋势窗口", type="int", default=20, min=5, max=120
        ),
        "rsi_period": ParamSpec(
            label="RSI周期", type="int", default=14, min=5, max=60
        ),
        "volume_window": ParamSpec(
            label="成交量窗口", type="int", default=20, min=5, max=120
        ),
        "volume_mult": ParamSpec(
            label="成交量倍数", type="float", default=1.5, min=1.0, max=5.0
        ),
        "score_threshold": ParamSpec(
            label="分数阈值", type="int", default=2, min=1, max=3
        ),
    }

    def bars_needed(self) -> int:
        return max(
            self.params["trend_window"],
            self.params["rsi_period"],
            self.params["volume_window"],
        ) + 5

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        trend_window = self.params["trend_window"]
        rsi_period = self.params["rsi_period"]
        volume_window = self.params["volume_window"]
        volume_mult = self.params["volume_mult"]
        threshold = self.params["score_threshold"]

        # Trend score: MA slope positive
        ma = calc_ma(df["close"], trend_window)
        trend_score = 1 if ma.iloc[-1] > ma.iloc[-2] else 0

        # RSI score: not overbought for long, not oversold for short
        rsi = calc_rsi(df["close"], window=rsi_period)
        curr_rsi = rsi.iloc[-1]
        rsi_bull = 1 if curr_rsi > 50 else 0
        rsi_bear = 1 if curr_rsi < 50 else 0

        # Volume score: volume spike
        avg_volume = df["volume"].rolling(window=volume_window).mean()
        volume_score = (
            1 if df["volume"].iloc[-1] > volume_mult * avg_volume.iloc[-1] else 0
        )

        bull_score = trend_score + rsi_bull + volume_score
        bear_score = (1 - trend_score) + rsi_bear + volume_score

        if bull_score >= threshold:
            return SignalResult(
                signal_type="BUY",
                strength=self._clamp_strength(bull_score * 33),
                metadata={
                    "trend_score": trend_score,
                    "rsi": round(curr_rsi, 2),
                    "volume_score": volume_score,
                    "total_score": bull_score,
                },
            )
        if bear_score >= threshold:
            return SignalResult(
                signal_type="SELL",
                strength=self._clamp_strength(bear_score * 33),
                metadata={
                    "trend_score": 1 - trend_score,
                    "rsi": round(curr_rsi, 2),
                    "volume_score": volume_score,
                    "total_score": bear_score,
                },
            )

        return SignalResult(
            signal_type="HOLD",
            strength=50,
            metadata={
                "rsi": round(curr_rsi, 2),
                "bull_score": bull_score,
                "bear_score": bear_score,
            },
        )

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        trend_window = self.params["trend_window"]
        rsi_period = self.params["rsi_period"]
        volume_window = self.params["volume_window"]
        volume_mult = self.params["volume_mult"]
        threshold = self.params["score_threshold"]

        ma = calc_ma(df["close"], trend_window)
        trend_up = ma > ma.shift(1)

        rsi = calc_rsi(df["close"], window=rsi_period)
        rsi_bull = rsi > 50
        rsi_bear = rsi < 50

        avg_volume = df["volume"].rolling(window=volume_window).mean()
        volume_spike = df["volume"] > volume_mult * avg_volume

        bull_score = trend_up.astype(int) + rsi_bull.astype(int) + volume_spike.astype(int)
        bear_score = (~trend_up).astype(int) + rsi_bear.astype(int) + volume_spike.astype(int)

        signals = pd.Series(0, index=df.index)
        signals[bull_score >= threshold] = 1
        signals[bear_score >= threshold] = -1
        return signals
