"""Event-driven strategy placeholder."""

import pandas as pd

from app.strategies.base import ParamSpec, SignalResult, Strategy, register_strategy


@register_strategy
class EventDrivenStrategy(Strategy):
    """Event-driven strategy placeholder.

    Currently returns HOLD with event-type metadata. Will be wired to the
    news/sentiment pipeline and corporate-action/earnings events in a
    future sprint.
    """

    strategy_type = "event_driven"
    name = "事件驱动"
    description = "基于财报、资讯、宏观事件的交易信号（占位实现）"
    family = "event"
    param_specs = {
        "event_types": ParamSpec(
            label="事件类型",
            type="choice",
            default="earnings",
            options=["earnings", "news", "macro"],
            description="关注的事件类型",
        ),
        "lookback_days": ParamSpec(
            label="回望天数", type="int", default=5, min=1, max=30
        ),
    }
    min_bars = 1

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        event_type = self.params.get("event_types", "earnings")
        lookback = self.params.get("lookback_days", 5)

        return SignalResult(
            signal_type="HOLD",
            strength=50,
            metadata={
                "event_type": event_type,
                "lookback_days": lookback,
                "note": "placeholder - event source not yet wired",
            },
        )

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(0, index=df.index)
