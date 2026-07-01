"""Cross-sectional / ranking strategy implementations."""

from datetime import date
from typing import Any

import pandas as pd

from app.strategies.base import ParamSpec, SignalResult, Strategy, register_strategy


@register_strategy
class MomentumRankStrategy(Strategy):
    """Cross-sectional momentum rank strategy.

    Given a universe of instruments, rank by N-day momentum and emit BUY
    signals for the top-N instruments and SELL signals for the bottom-N.
    """

    strategy_type = "momentum_rank"
    name = "动量排名"
    description = "在标的中按N日动量排名，前N买入、后N卖出"
    family = "cross_sectional"
    param_specs = {
        "rank_window": ParamSpec(
            label="排名窗口", type="int", default=20, min=5, max=252
        ),
        "top_n": ParamSpec(label="多头数量", type="int", default=5, min=1, max=100),
        "bottom_n": ParamSpec(label="空头数量", type="int", default=5, min=1, max=100),
        "min_universe_size": ParamSpec(
            label="最小universe大小", type="int", default=10, min=2, max=1000
        ),
    }

    def bars_needed(self) -> int:
        return self.params["rank_window"] + 5

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        """Single-instrument fallback: not meaningful for cross-sectional.

        Returns HOLD because ranking requires a universe.
        """
        return SignalResult(
            signal_type="HOLD",
            strength=50,
            metadata={"note": "cross_sectional strategy requires a universe"},
        )

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        """Single-instrument series fallback: all HOLD.

        Cross-sectional ranking requires a universe; for a single instrument
        backtest we return a flat HOLD series.
        """
        return pd.Series(0, index=df.index)

    def generate_universe(
        self,
        df: pd.DataFrame,
        trade_date: date,
    ) -> list[dict[str, Any]]:
        """Generate cross-sectional signals for a universe of instruments.

        Args:
            df: DataFrame with columns including ``etf_code``, ``trade_date``,
                ``close``, sorted by ``etf_code`` and ``trade_date`` ascending.
            trade_date: The target date for signal generation. The latest
                available bar on or before this date is used for each instrument.

        Returns:
            List of signal dicts with ``etf_code``, ``type``, ``strength``,
            and ``metadata`` keys.
        """
        rank_window = self.params["rank_window"]
        top_n = self.params["top_n"]
        bottom_n = self.params["bottom_n"]
        min_size = self.params["min_universe_size"]

        # Use the latest available bar on or before trade_date for each code
        df = df[df["trade_date"] <= pd.Timestamp(trade_date)]
        if df.empty:
            return []

        latest = df.sort_values("trade_date").groupby("etf_code").last().reset_index()
        if len(latest) < min_size:
            return []

        # Compute momentum over the rank window for each instrument
        def _calc_momentum(group: pd.DataFrame) -> float:
            window_df = group.tail(rank_window + 1)
            if len(window_df) < 2:
                return float("nan")
            old = window_df["close"].iloc[0]
            new = window_df["close"].iloc[-1]
            if pd.isna(old) or old == 0:
                return float("nan")
            return (new - old) / old

        momentum_map = {}
        for code, group in df.groupby("etf_code"):
            momentum_map[code] = _calc_momentum(group)

        latest["momentum"] = latest["etf_code"].map(momentum_map)
        latest = latest.dropna(subset=["momentum"])

        if len(latest) < min_size:
            return []

        latest = latest.sort_values("momentum", ascending=False).reset_index(drop=True)
        top_codes = set(latest.head(top_n)["etf_code"])
        bottom_codes = set(latest.tail(bottom_n)["etf_code"])

        signals = []
        for _, row in latest.iterrows():
            code = row["etf_code"]
            momentum = row["momentum"]
            if code in top_codes:
                signals.append({
                    "etf_code": code,
                    "type": "BUY",
                    "strength": self._clamp_strength(abs(momentum) * 1000),
                    "metadata": {"momentum": round(momentum, 4), "rank": "top"},
                })
            elif code in bottom_codes:
                signals.append({
                    "etf_code": code,
                    "type": "SELL",
                    "strength": self._clamp_strength(abs(momentum) * 1000),
                    "metadata": {"momentum": round(momentum, 4), "rank": "bottom"},
                })

        return signals
