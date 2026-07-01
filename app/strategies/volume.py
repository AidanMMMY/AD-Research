"""Volume-based strategy implementations."""

import pandas as pd

from app.strategies.base import ParamSpec, SignalResult, Strategy, register_strategy


@register_strategy
class VolumeBreakoutStrategy(Strategy):
    """Volume breakout strategy.

    BUY when volume spikes above N times the average volume and the close
    is higher than the previous close. SELL when volume spikes with a lower
    close.
    """

    strategy_type = "volume_breakout"
    name = "成交量突破"
    description = "成交量放大N倍且价格确认方向时买入/卖出"
    family = "volume"
    param_specs = {
        "volume_window": ParamSpec(
            label="成交量均值窗口", type="int", default=20, min=5, max=120
        ),
        "volume_multiplier": ParamSpec(
            label="成交量倍数", type="float", default=2.0, min=1.0, max=10.0
        ),
        "price_confirm": ParamSpec(
            label="价格确认", type="bool", default=True
        ),
    }

    def bars_needed(self) -> int:
        return self.params["volume_window"] + 5

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        window = self.params["volume_window"]
        multiplier = self.params["volume_multiplier"]
        price_confirm = self.params["price_confirm"]

        avg_volume = df["volume"].rolling(window=window).mean()
        prev_close = df["close"].iloc[-2]
        curr_close = df["close"].iloc[-1]
        curr_volume = df["volume"].iloc[-1]
        curr_avg = avg_volume.iloc[-1]

        if pd.isna(curr_avg) or curr_avg == 0:
            return None

        volume_spike = curr_volume > multiplier * curr_avg
        if not volume_spike:
            return SignalResult(
                signal_type="HOLD",
                strength=50,
                metadata={
                    "volume_ratio": round(curr_volume / curr_avg, 2),
                },
            )

        if not price_confirm or curr_close > prev_close:
            return SignalResult(
                signal_type="BUY",
                strength=self._clamp_strength((curr_volume / curr_avg) * 20),
                metadata={"volume_ratio": round(curr_volume / curr_avg, 2)},
            )

        return SignalResult(
            signal_type="SELL",
            strength=self._clamp_strength((curr_volume / curr_avg) * 20),
            metadata={"volume_ratio": round(curr_volume / curr_avg, 2)},
        )

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        window = self.params["volume_window"]
        multiplier = self.params["volume_multiplier"]
        price_confirm = self.params["price_confirm"]

        avg_volume = df["volume"].rolling(window=window).mean()
        volume_spike = df["volume"] > multiplier * avg_volume

        signals = pd.Series(0, index=df.index)
        if price_confirm:
            signals[volume_spike & (df["close"] > df["close"].shift(1))] = 1
            signals[volume_spike & (df["close"] < df["close"].shift(1))] = -1
        else:
            signals[volume_spike] = 1
        return signals


@register_strategy
class OBVTrendStrategy(Strategy):
    """On-Balance Volume (OBV) trend strategy.

    BUY when the OBV slope exceeds the positive threshold.
    SELL when the OBV slope falls below the negative threshold.
    """

    strategy_type = "obv_trend"
    name = "OBV趋势"
    description = "OBV斜率超过阈值买入，低于负阈值卖出"
    family = "volume"
    param_specs = {
        "obv_slope_window": ParamSpec(
            label="OBV斜率窗口", type="int", default=10, min=3, max=60
        ),
        "slope_threshold": ParamSpec(
            label="斜率阈值", type="float", default=0.01, min=0.0, max=0.2
        ),
    }

    def bars_needed(self) -> int:
        return self.params["obv_slope_window"] + 20

    def _calc_obv(self, df: pd.DataFrame) -> pd.Series:
        """Calculate the OBV series."""
        close_diff = df["close"].diff()
        volume = df["volume"].fillna(0)
        obv = pd.Series(0.0, index=df.index)

        obv[close_diff > 0] = volume[close_diff > 0]
        obv[close_diff < 0] = -volume[close_diff < 0]
        return obv.cumsum()

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        window = self.params["obv_slope_window"]
        threshold = self.params["slope_threshold"]

        obv = self._calc_obv(df)
        obv_ma = obv.rolling(window=window).mean()
        obv_std = obv.rolling(window=window).std()

        prev_obv = obv.iloc[-2]
        curr_obv = obv.iloc[-1]
        prev_ma = obv_ma.iloc[-2]
        curr_ma = obv_ma.iloc[-1]

        if pd.isna(prev_ma) or prev_ma == 0:
            return None

        # Normalized slope of OBV relative to its moving average
        slope = (curr_obv - prev_obv) / abs(prev_ma)

        if slope > threshold:
            return SignalResult(
                signal_type="BUY",
                strength=self._clamp_strength(abs(slope) * 1000),
                metadata={"obv_slope": round(slope, 4)},
            )
        if slope < -threshold:
            return SignalResult(
                signal_type="SELL",
                strength=self._clamp_strength(abs(slope) * 1000),
                metadata={"obv_slope": round(slope, 4)},
            )

        return SignalResult(
            signal_type="HOLD",
            strength=50,
            metadata={"obv_slope": round(slope, 4)},
        )

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        window = self.params["obv_slope_window"]
        threshold = self.params["slope_threshold"]

        obv = self._calc_obv(df)
        obv_ma = obv.rolling(window=window).mean()
        obv_ma_shifted = obv_ma.shift(1)

        # Avoid division by zero
        slope = (obv - obv.shift(1)) / obv_ma_shifted.replace(0, pd.NA)
        signals = pd.Series(0, index=df.index)
        signals[slope > threshold] = 1
        signals[slope < -threshold] = -1
        return signals
