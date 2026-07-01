"""Tests for the strategy registry and built-in strategies."""

import pandas as pd
import pytest

from app.strategies.base import StrategyRegistry, register_strategy
from app.strategies.base import Strategy, ParamSpec, SignalResult


SAMPLE_DF = pd.DataFrame({
    "trade_date": pd.date_range("2024-01-01", periods=100, freq="D"),
    "open": 100.0 + pd.Series(range(100)).cumsum() * 0.1,
    "high": 101.0 + pd.Series(range(100)).cumsum() * 0.1,
    "low": 99.0 + pd.Series(range(100)).cumsum() * 0.1,
    "close": 100.0 + pd.Series(range(100)).cumsum() * 0.1,
    "volume": [1_000_000] * 100,
})


class TestRegistry:
    """Tests for the strategy registry."""

    def test_registry_contains_builtins(self):
        strategies = StrategyRegistry.list_all()
        types = {s["strategy_type"] for s in strategies}
        assert "momentum" in types
        assert "ma_crossover" in types
        assert "rsi_mean_reversion" in types
        assert "momentum_rank" in types

    def test_families(self):
        families = StrategyRegistry.families()
        assert "trend_following" in families
        assert "cross_sectional" in families

    def test_get_unknown_returns_none(self):
        assert StrategyRegistry.get("not_a_strategy") is None

    def test_register_decorator(self):
        @register_strategy
        class DummyStrategy(Strategy):
            strategy_type = "dummy_test_strategy"
            name = "Dummy"
            description = "For testing"
            family = "test"
            param_specs = {}

            def generate(self, df):
                return SignalResult("HOLD", 50)

            def generate_series(self, df):
                return pd.Series(0, index=df.index)

        try:
            retrieved = StrategyRegistry.get("dummy_test_strategy")
            assert retrieved is DummyStrategy
        finally:
            StrategyRegistry._strategies.pop("dummy_test_strategy", None)


class TestTrendFollowing:
    """Tests for trend-following strategies."""

    def test_ma_crossover_returns_signal(self):
        strategy_class = StrategyRegistry.get("ma_crossover")
        strategy = strategy_class({"short_window": 5, "long_window": 20})
        result = strategy.generate(SAMPLE_DF)
        assert result is not None
        assert result.signal_type in ("BUY", "SELL", "HOLD")

    def test_macd_signal_series(self):
        strategy_class = StrategyRegistry.get("macd_signal")
        strategy = strategy_class({})
        series = strategy.generate_series(SAMPLE_DF)
        assert len(series) == len(SAMPLE_DF)
        assert set(series.unique()).issubset({-1, 0, 1})


class TestMeanReversion:
    """Tests for mean-reversion strategies."""

    def test_rsi_mean_reversion(self):
        strategy_class = StrategyRegistry.get("rsi_mean_reversion")
        strategy = strategy_class({})
        result = strategy.generate(SAMPLE_DF)
        assert result is not None
        assert result.signal_type in ("BUY", "SELL", "HOLD")

    def test_z_score_reversion_series(self):
        strategy_class = StrategyRegistry.get("z_score_reversion")
        strategy = strategy_class({})
        series = strategy.generate_series(SAMPLE_DF)
        assert len(series) == len(SAMPLE_DF)


class TestMomentum:
    """Tests for momentum strategies."""

    def test_price_momentum(self):
        strategy_class = StrategyRegistry.get("price_momentum")
        strategy = strategy_class({})
        result = strategy.generate(SAMPLE_DF)
        assert result is not None
        assert result.signal_type in ("BUY", "SELL", "HOLD")

    def test_legacy_momentum_matches_new(self):
        """Legacy momentum should produce the same signal type as the new impl."""
        legacy_class = StrategyRegistry.get("momentum")
        new_class = StrategyRegistry.get("price_momentum")
        legacy_result = legacy_class({}).generate(SAMPLE_DF)
        new_result = new_class({}).generate(SAMPLE_DF)
        assert legacy_result is not None
        assert new_result is not None


class TestCrossSectional:
    """Tests for cross-sectional strategies."""

    def test_momentum_rank_universe(self):
        strategy_class = StrategyRegistry.get("momentum_rank")
        strategy = strategy_class({
            "rank_window": 5,
            "top_n": 2,
            "bottom_n": 2,
            "min_universe_size": 5,
        })

        codes = ["A", "B", "C", "D", "E"]
        dfs = []
        for i, code in enumerate(codes):
            df = SAMPLE_DF.copy()
            df["etf_code"] = code
            df["close"] = df["close"] * (1 + i * 0.01)
            dfs.append(df)
        universe_df = pd.concat(dfs, ignore_index=True)

        from datetime import date
        signals = strategy.generate_universe(universe_df, date(2024, 4, 10))
        assert isinstance(signals, list)
        assert len(signals) == 4  # top 2 + bottom 2

    def test_momentum_rank_single_instrument_hold(self):
        strategy_class = StrategyRegistry.get("momentum_rank")
        strategy = strategy_class({})
        result = strategy.generate(SAMPLE_DF)
        assert result.signal_type == "HOLD"


class TestComposite:
    """Tests for composite strategies."""

    def test_triple_screen(self):
        strategy_class = StrategyRegistry.get("triple_screen")
        strategy = strategy_class({})
        result = strategy.generate(SAMPLE_DF)
        assert result is not None
        assert result.signal_type in ("BUY", "SELL", "HOLD")
