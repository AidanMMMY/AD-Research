"""Event-driven strategy.

Generates trading signals from an event layer (currently news sentiment)
aggregated by :class:`app.services.event_data_service.EventDataService`.

The strategy needs a DB session, which the strategy engine passes in via the
``db`` constructor argument. When no session is available (e.g. metadata-only
listing or a price-only backtest harness) it degrades gracefully to HOLD.

Signal rules (news sentiment, ``avg_sentiment`` on a 0..1 scale):
  - ``avg_sentiment > 0.6`` and ``count >= 3`` -> BUY
  - ``avg_sentiment < 0.4`` and ``count >= 3`` -> SELL
  - otherwise                                  -> HOLD
"""

from datetime import date

import pandas as pd

from app.strategies.base import ParamSpec, SignalResult, Strategy, register_strategy

_MIN_EVENTS = 3
_BUY_THRESHOLD = 0.6
_SELL_THRESHOLD = 0.4


@register_strategy
class EventDrivenStrategy(Strategy):
    """Event-driven strategy backed by the news-sentiment event layer."""

    strategy_type = "event_driven"
    name = "事件驱动"
    description = "基于资讯情绪的事件驱动信号：聚合回望窗口内的新闻情绪，情绪偏多时买入、偏空时卖出。"
    family = "event"
    param_specs = {
        "event_types": ParamSpec(
            label="事件类型",
            type="choice",
            default="news",
            options=["news", "earnings", "macro"],
            description="关注的事件类型（当前 v1 仅实现 news）",
        ),
        "lookback_days": ParamSpec(
            label="回望天数", type="int", default=5, min=1, max=30
        ),
    }
    min_bars = 1

    def _resolve_date(self, df: pd.DataFrame) -> date:
        """Best-effort as-of date from the bar frame, else today."""
        if df is not None and not df.empty and "trade_date" in df.columns:
            value = df["trade_date"].iloc[-1]
            ts = pd.Timestamp(value)
            if not pd.isna(ts):
                return ts.date()
        return date.today()

    def _resolve_code(self, df: pd.DataFrame) -> str | None:
        """Best-effort instrument code from the bar frame."""
        if df is not None and not df.empty and "etf_code" in df.columns:
            code = df["etf_code"].iloc[-1]
            if code:
                return str(code)
        return None

    def _signal_for(self, code: str, as_of: date) -> SignalResult:
        """Compute a signal for one instrument/date from the event layer."""
        event_type = self.params.get("event_types", "news")
        lookback = int(self.params.get("lookback_days", 5))

        # v1: only news sentiment is wired. Other types fall through to HOLD.
        if event_type != "news" or self.db is None or not code:
            return SignalResult(
                signal_type="HOLD",
                strength=50,
                metadata={
                    "event_type": event_type,
                    "lookback_days": lookback,
                    "reason": (
                        "no db session"
                        if self.db is None
                        else f"event_type '{event_type}' not implemented in v1"
                        if event_type != "news"
                        else "no instrument code"
                    ),
                },
            )

        # Imported lazily so the strategy module stays importable without
        # a DB layer (e.g. for metadata listing on the frontend).
        from app.services.event_data_service import EventDataService

        agg = EventDataService(self.db).get_news_sentiment(code, as_of, lookback)
        avg = agg["avg_sentiment"]
        count = agg["count"]

        metadata = {
            "event_type": "news",
            "lookback_days": lookback,
            "avg_sentiment": round(avg, 4),
            "count": count,
            "positive": agg["positive"],
            "negative": agg["negative"],
            "neutral": agg["neutral"],
        }

        if avg > _BUY_THRESHOLD and count >= _MIN_EVENTS:
            return SignalResult(
                signal_type="BUY",
                strength=self._clamp_strength(avg * 100),
                metadata=metadata,
            )
        if avg < _SELL_THRESHOLD and count >= _MIN_EVENTS:
            return SignalResult(
                signal_type="SELL",
                strength=self._clamp_strength((1 - avg) * 100),
                metadata=metadata,
            )
        return SignalResult(signal_type="HOLD", strength=50, metadata=metadata)

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        code = self._resolve_code(df)
        as_of = self._resolve_date(df)
        return self._signal_for(code, as_of)

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        """Per-bar signal series for backtesting (1 BUY / -1 SELL / 0 HOLD)."""
        if df is None or df.empty:
            return pd.Series(dtype="int64")

        code = self._resolve_code(df)
        if self.db is None or not code or self.params.get("event_types", "news") != "news":
            return pd.Series(0, index=df.index)

        from app.services.event_data_service import EventDataService

        service = EventDataService(self.db)
        lookback = int(self.params.get("lookback_days", 5))

        values = []
        for _, row in df.iterrows():
            ts = pd.Timestamp(row.get("trade_date")) if "trade_date" in df.columns else pd.NaT
            as_of = ts.date() if not pd.isna(ts) else date.today()
            agg = service.get_news_sentiment(code, as_of, lookback)
            avg, count = agg["avg_sentiment"], agg["count"]
            if avg > _BUY_THRESHOLD and count >= _MIN_EVENTS:
                values.append(1)
            elif avg < _SELL_THRESHOLD and count >= _MIN_EVENTS:
                values.append(-1)
            else:
                values.append(0)
        return pd.Series(values, index=df.index)
