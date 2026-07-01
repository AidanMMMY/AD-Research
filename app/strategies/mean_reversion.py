"""Mean-reversion strategy implementations."""

import pandas as pd

from app.data.indicators.technical import calc_bollinger, calc_rsi
from app.strategies.base import ParamSpec, SignalResult, Strategy, register_strategy


@register_strategy
class LegacyMeanReversionStrategy(Strategy):
    """Legacy mean-reversion strategy (backward-compatible with old configs)."""

    strategy_type = "mean_reversion"
    name = "均值回归"
    description = "基于价格偏离均值的反转策略"
    family = "mean_reversion"
    param_specs = {
        "lookback_window": ParamSpec(
            label="回望窗口", type="int", default=20, min=5, max=60
        ),
        "z_score_threshold": ParamSpec(
            label="Z-Score阈值", type="float", default=2.0, min=1.0, max=4.0
        ),
        "holding_period": ParamSpec(
            label="持有周期", type="int", default=5, min=1, max=20
        ),
    }

    def bars_needed(self) -> int:
        return self.params["lookback_window"] + 5

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        window = self.params["lookback_window"]
        z_threshold = self.params["z_score_threshold"]

        recent = df.tail(window)
        mean = recent["close"].mean()
        std = recent["close"].std()
        latest = df.iloc[-1]["close"]

        if std <= 0 or pd.isna(std):
            return None

        z_score = (latest - mean) / std
        if z_score < -z_threshold:
            return SignalResult(
                signal_type="BUY",
                strength=self._clamp_strength(abs(z_score) * 30),
                metadata={"z_score": round(z_score, 3)},
            )
        if z_score > z_threshold:
            return SignalResult(
                signal_type="SELL",
                strength=self._clamp_strength(abs(z_score) * 30),
                metadata={"z_score": round(z_score, 3)},
            )
        return SignalResult(
            signal_type="HOLD",
            strength=50,
            metadata={"z_score": round(z_score, 3)},
        )

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        window = self.params["lookback_window"]
        z_threshold = self.params["z_score_threshold"]
        ma = df["close"].rolling(window).mean()
        std = df["close"].rolling(window).std()
        z_score = (df["close"] - ma) / std
        signals = pd.Series(0, index=df.index)
        signals[z_score < -z_threshold] = 1
        signals[z_score > z_threshold] = -1
        return signals


@register_strategy
class LegacyRSIStrategy(Strategy):
    """Legacy RSI strategy (backward-compatible with old configs)."""

    strategy_type = "rsi"
    name = "RSI策略"
    description = "基于RSI超买超卖的动量策略"
    family = "mean_reversion"
    param_specs = {
        "rsi_period": ParamSpec(
            label="RSI周期", type="int", default=14, min=5, max=30
        ),
        "overbought": ParamSpec(
            label="超买阈值", type="int", default=70, min=60, max=90
        ),
        "oversold": ParamSpec(
            label="超卖阈值", type="int", default=30, min=10, max=40
        ),
        "holding_period": ParamSpec(
            label="持有周期", type="int", default=5, min=1, max=20
        ),
    }

    def bars_needed(self) -> int:
        return self.params["rsi_period"] + 5

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        period = self.params["rsi_period"]
        overbought = self.params["overbought"]
        oversold = self.params["oversold"]

        rsi = calc_rsi(df["close"], window=period)
        curr_rsi = rsi.iloc[-1]

        if pd.isna(curr_rsi):
            return None

        if curr_rsi < oversold:
            return SignalResult(
                signal_type="BUY",
                strength=self._clamp_strength((oversold - curr_rsi) * 3),
                metadata={"rsi": round(curr_rsi, 2)},
            )
        if curr_rsi > overbought:
            return SignalResult(
                signal_type="SELL",
                strength=self._clamp_strength((curr_rsi - overbought) * 3),
                metadata={"rsi": round(curr_rsi, 2)},
            )
        return SignalResult(
            signal_type="HOLD",
            strength=50,
            metadata={"rsi": round(curr_rsi, 2)},
        )

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        period = self.params["rsi_period"]
        overbought = self.params["overbought"]
        oversold = self.params["oversold"]
        rsi = calc_rsi(df["close"], window=period)
        signals = pd.Series(0, index=df.index)
        signals[rsi < oversold] = 1
        signals[rsi > overbought] = -1
        return signals


@register_strategy
class RSIMeanReversionStrategy(Strategy):
    """RSI mean-reversion strategy.

    BUY when RSI falls below the oversold threshold.
    SELL when RSI rises above the overbought threshold.
    """

    strategy_type = "rsi_mean_reversion"
    name = "RSI均值回归"
    description = "RSI超卖买入，超买卖出"
    family = "mean_reversion"
    param_specs = {
        "rsi_period": ParamSpec(
            label="RSI周期", type="int", default=14, min=5, max=30
        ),
        "oversold": ParamSpec(
            label="超卖阈值", type="int", default=30, min=10, max=40
        ),
        "overbought": ParamSpec(
            label="超买阈值", type="int", default=70, min=60, max=90
        ),
    }

    def bars_needed(self) -> int:
        return self.params["rsi_period"] + 5

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        period = self.params["rsi_period"]
        oversold = self.params["oversold"]
        overbought = self.params["overbought"]

        rsi = calc_rsi(df["close"], window=period)
        curr_rsi = rsi.iloc[-1]

        if pd.isna(curr_rsi):
            return None

        if curr_rsi < oversold:
            return SignalResult(
                signal_type="BUY",
                strength=self._clamp_strength((oversold - curr_rsi) * 3),
                metadata={"rsi": round(curr_rsi, 2)},
            )
        if curr_rsi > overbought:
            return SignalResult(
                signal_type="SELL",
                strength=self._clamp_strength((curr_rsi - overbought) * 3),
                metadata={"rsi": round(curr_rsi, 2)},
            )

        return SignalResult(signal_type="HOLD", strength=50, metadata={"rsi": round(curr_rsi, 2)})

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        period = self.params["rsi_period"]
        oversold = self.params["oversold"]
        overbought = self.params["overbought"]

        rsi = calc_rsi(df["close"], window=period)
        signals = pd.Series(0, index=df.index)
        signals[rsi < oversold] = 1
        signals[rsi > overbought] = -1
        return signals


@register_strategy
class BBMeanReversionStrategy(Strategy):
    """Bollinger Bands mean-reversion strategy.

    BUY when the close touches the lower band.
    SELL when the close touches the upper band.
    """

    strategy_type = "bb_mean_reversion"
    name = "布林带均值回归"
    description = "触及布林带下轨买入，触及上轨卖出"
    family = "mean_reversion"
    param_specs = {
        "window": ParamSpec(label="窗口", type="int", default=20, min=5, max=60),
        "num_std": ParamSpec(
            label="标准差倍数", type="float", default=2.0, min=0.5, max=4.0
        ),
    }

    def bars_needed(self) -> int:
        return self.params["window"] + 5

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        window = self.params["window"]
        num_std = self.params["num_std"]

        upper, lower = calc_bollinger(df["close"], window=window, num_std=num_std)
        ma = df["close"].rolling(window=window, min_periods=1).mean()

        curr_close = df["close"].iloc[-1]
        curr_upper = upper.iloc[-1]
        curr_lower = lower.iloc[-1]
        curr_ma = ma.iloc[-1]

        if pd.isna(curr_upper) or pd.isna(curr_lower):
            return None

        if curr_close <= curr_lower:
            strength = self._clamp_strength((curr_lower - curr_close) / (curr_upper - curr_lower) * 500)
            return SignalResult(
                signal_type="BUY",
                strength=strength,
                metadata={
                    "upper": round(curr_upper, 4),
                    "lower": round(curr_lower, 4),
                    "ma": round(curr_ma, 4),
                },
            )
        if curr_close >= curr_upper:
            strength = self._clamp_strength((curr_close - curr_upper) / (curr_upper - curr_lower) * 500)
            return SignalResult(
                signal_type="SELL",
                strength=strength,
                metadata={
                    "upper": round(curr_upper, 4),
                    "lower": round(curr_lower, 4),
                    "ma": round(curr_ma, 4),
                },
            )

        return SignalResult(
            signal_type="HOLD",
            strength=50,
            metadata={
                "upper": round(curr_upper, 4),
                "lower": round(curr_lower, 4),
            },
        )

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        window = self.params["window"]
        num_std = self.params["num_std"]

        upper, lower = calc_bollinger(df["close"], window=window, num_std=num_std)
        signals = pd.Series(0, index=df.index)
        signals[df["close"] <= lower] = 1
        signals[df["close"] >= upper] = -1
        return signals


@register_strategy
class ZScoreReversionStrategy(Strategy):
    """Z-score mean-reversion strategy.

    BUY when the price z-score falls below -threshold.
    SELL when the z-score rises above threshold.
    """

    strategy_type = "z_score_reversion"
    name = "Z-Score均值回归"
    description = "价格偏离滚动均值超过阈值后反向交易"
    family = "mean_reversion"
    param_specs = {
        "lookback_window": ParamSpec(
            label="回望窗口", type="int", default=20, min=5, max=120
        ),
        "z_threshold": ParamSpec(
            label="Z-Score阈值", type="float", default=2.0, min=0.5, max=4.0
        ),
    }

    def bars_needed(self) -> int:
        return self.params["lookback_window"] + 5

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        window = self.params["lookback_window"]
        threshold = self.params["z_threshold"]

        ma = df["close"].rolling(window=window).mean()
        std = df["close"].rolling(window=window).std()
        z_score = (df["close"] - ma) / std

        curr_z = z_score.iloc[-1]
        if pd.isna(curr_z):
            return None

        if curr_z < -threshold:
            return SignalResult(
                signal_type="BUY",
                strength=self._clamp_strength(abs(curr_z) * 30),
                metadata={"z_score": round(curr_z, 3)},
            )
        if curr_z > threshold:
            return SignalResult(
                signal_type="SELL",
                strength=self._clamp_strength(abs(curr_z) * 30),
                metadata={"z_score": round(curr_z, 3)},
            )

        return SignalResult(
            signal_type="HOLD", strength=50, metadata={"z_score": round(curr_z, 3)}
        )

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        window = self.params["lookback_window"]
        threshold = self.params["z_threshold"]

        ma = df["close"].rolling(window=window).mean()
        std = df["close"].rolling(window=window).std()
        z_score = (df["close"] - ma) / std

        signals = pd.Series(0, index=df.index)
        signals[z_score < -threshold] = 1
        signals[z_score > threshold] = -1
        return signals
