"""Momentum strategy implementations."""

import pandas as pd

from app.strategies.base import ParamSpec, SignalResult, Strategy, register_strategy


@register_strategy
class LegacyMomentumStrategy(Strategy):
    """Legacy momentum strategy (backward-compatible with old configs)."""

    strategy_type = "momentum"
    name = "动量策略"
    description = "基于价格动量的趋势跟踪策略"
    family = "momentum"
    param_specs = {
        "momentum_window": ParamSpec(
            label="动量窗口", type="int", default=20, min=5, max=252
        ),
        "threshold": ParamSpec(
            label="动量阈值", type="float", default=0.05, min=0.01, max=0.5
        ),
        "holding_period": ParamSpec(
            label="持有周期", type="int", default=20, min=5, max=60
        ),
    }

    def bars_needed(self) -> int:
        return self.params["momentum_window"] + 5

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        window = self.params["momentum_window"]
        threshold = self.params["threshold"]

        if len(df) < window + 1:
            return None

        prev_close = df.iloc[-window - 1]["close"]
        curr_close = df.iloc[-1]["close"]
        if prev_close == 0 or pd.isna(prev_close):
            return None

        momentum = (curr_close - prev_close) / prev_close
        if momentum > threshold:
            return SignalResult(
                signal_type="BUY",
                strength=self._clamp_strength(momentum * 100),
                metadata={"momentum": round(momentum, 4)},
            )
        if momentum < -threshold:
            return SignalResult(
                signal_type="SELL",
                strength=self._clamp_strength(abs(momentum) * 100),
                metadata={"momentum": round(momentum, 4)},
            )
        return SignalResult(
            signal_type="HOLD",
            strength=50,
            metadata={"momentum": round(momentum, 4)},
        )

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        window = self.params["momentum_window"]
        threshold = self.params["threshold"]
        momentum = df["close"].pct_change(window)
        signals = pd.Series(0, index=df.index)
        signals[momentum > threshold] = 1
        signals[momentum < -threshold] = -1
        return signals


@register_strategy
class PriceMomentumStrategy(Strategy):
    """Price momentum strategy.

    BUY when the N-day return exceeds the positive threshold.
    SELL when it falls below the negative threshold.
    """

    strategy_type = "price_momentum"
    name = "价格动量"
    description = "N日收益率超过阈值买入，低于负阈值卖出"
    family = "momentum"
    param_specs = {
        "momentum_window": ParamSpec(
            label="动量窗口", type="int", default=20, min=5, max=252
        ),
        "threshold": ParamSpec(
            label="动量阈值", type="float", default=0.05, min=0.01, max=0.5
        ),
    }

    def bars_needed(self) -> int:
        return self.params["momentum_window"] + 5

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        window = self.params["momentum_window"]
        threshold = self.params["threshold"]

        momentum = df["close"].pct_change(window)
        curr_momentum = momentum.iloc[-1]

        if pd.isna(curr_momentum):
            return None

        if curr_momentum > threshold:
            return SignalResult(
                signal_type="BUY",
                strength=self._clamp_strength(abs(curr_momentum) * 1000),
                metadata={"momentum": round(curr_momentum, 4)},
            )
        if curr_momentum < -threshold:
            return SignalResult(
                signal_type="SELL",
                strength=self._clamp_strength(abs(curr_momentum) * 1000),
                metadata={"momentum": round(curr_momentum, 4)},
            )

        return SignalResult(
            signal_type="HOLD", strength=50, metadata={"momentum": round(curr_momentum, 4)}
        )

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        window = self.params["momentum_window"]
        threshold = self.params["threshold"]

        momentum = df["close"].pct_change(window)
        signals = pd.Series(0, index=df.index)
        signals[momentum > threshold] = 1
        signals[momentum < -threshold] = -1
        return signals


@register_strategy
class MTFMomentumStrategy(Strategy):
    """Multi-timeframe momentum strategy.

    Combines short, medium, and long-term momentum into a weighted score.
    """

    strategy_type = "mtf_momentum"
    name = "多周期动量"
    description = "结合短、中、长期动量加权打分"
    family = "momentum"
    param_specs = {
        "short_weight": ParamSpec(
            label="短期权重", type="float", default=0.5, min=0.0, max=1.0
        ),
        "medium_weight": ParamSpec(
            label="中期权重", type="float", default=0.3, min=0.0, max=1.0
        ),
        "long_weight": ParamSpec(
            label="长期权重", type="float", default=0.2, min=0.0, max=1.0
        ),
        "threshold": ParamSpec(
            label="综合阈值", type="float", default=0.03, min=0.005, max=0.2
        ),
    }
    min_bars = 65

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        short_w = self.params["short_weight"]
        medium_w = self.params["medium_weight"]
        long_w = self.params["long_weight"]
        threshold = self.params["threshold"]

        short_mom = df["close"].pct_change(5)
        medium_mom = df["close"].pct_change(20)
        long_mom = df["close"].pct_change(60)

        score = (
            short_w * short_mom
            + medium_w * medium_mom
            + long_w * long_mom
        )
        curr_score = score.iloc[-1]

        if pd.isna(curr_score):
            return None

        if curr_score > threshold:
            return SignalResult(
                signal_type="BUY",
                strength=self._clamp_strength(abs(curr_score) * 1000),
                metadata={
                    "short_momentum": round(short_mom.iloc[-1], 4),
                    "medium_momentum": round(medium_mom.iloc[-1], 4),
                    "long_momentum": round(long_mom.iloc[-1], 4),
                    "score": round(curr_score, 4),
                },
            )
        if curr_score < -threshold:
            return SignalResult(
                signal_type="SELL",
                strength=self._clamp_strength(abs(curr_score) * 1000),
                metadata={
                    "short_momentum": round(short_mom.iloc[-1], 4),
                    "medium_momentum": round(medium_mom.iloc[-1], 4),
                    "long_momentum": round(long_mom.iloc[-1], 4),
                    "score": round(curr_score, 4),
                },
            )

        return SignalResult(
            signal_type="HOLD",
            strength=50,
            metadata={"score": round(curr_score, 4)},
        )

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        short_w = self.params["short_weight"]
        medium_w = self.params["medium_weight"]
        long_w = self.params["long_weight"]
        threshold = self.params["threshold"]

        score = (
            short_w * df["close"].pct_change(5)
            + medium_w * df["close"].pct_change(20)
            + long_w * df["close"].pct_change(60)
        )
        signals = pd.Series(0, index=df.index)
        signals[score > threshold] = 1
        signals[score < -threshold] = -1
        return signals


@register_strategy
class RateOfChangeStrategy(Strategy):
    """Rate of Change (ROC) strategy.

    BUY when the smoothed ROC crosses above zero.
    SELL when it crosses below zero.
    """

    strategy_type = "rate_of_change"
    name = "变动率"
    description = "ROC上穿零轴买入，下穿零轴卖出"
    family = "momentum"
    param_specs = {
        "roc_period": ParamSpec(label="ROC周期", type="int", default=12, min=2, max=60),
        "smoothing": ParamSpec(label="平滑周期", type="int", default=3, min=1, max=20),
    }

    def bars_needed(self) -> int:
        return self.params["roc_period"] + self.params["smoothing"] + 5

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        roc_period = self.params["roc_period"]
        smoothing = self.params["smoothing"]

        roc = (df["close"] / df["close"].shift(roc_period) - 1) * 100
        smoothed = roc.rolling(window=smoothing, min_periods=1).mean()

        prev = smoothed.iloc[-2]
        curr = smoothed.iloc[-1]

        if pd.isna(prev):
            return None

        if prev <= 0 < curr:
            return SignalResult(
                signal_type="BUY",
                strength=self._clamp_strength(abs(curr) * 10),
                metadata={"roc": round(curr, 3)},
            )
        if prev >= 0 > curr:
            return SignalResult(
                signal_type="SELL",
                strength=self._clamp_strength(abs(curr) * 10),
                metadata={"roc": round(curr, 3)},
            )

        return SignalResult(signal_type="HOLD", strength=50, metadata={"roc": round(curr, 3)})

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        roc_period = self.params["roc_period"]
        smoothing = self.params["smoothing"]

        roc = (df["close"] / df["close"].shift(roc_period) - 1) * 100
        smoothed = roc.rolling(window=smoothing, min_periods=1).mean()

        signals = pd.Series(0, index=df.index)
        signals[(smoothed.shift(1) <= 0) & (smoothed > 0)] = 1
        signals[(smoothed.shift(1) >= 0) & (smoothed < 0)] = -1
        return signals
