"""Strategy base class and registry.

Provides the abstract ``Strategy`` base class and ``StrategyRegistry``
used by all registered strategy implementations. The registry enables
discovery of strategy metadata (name, family, parameters) for both the
backend signal engine and the frontend strategy library.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

import pandas as pd


@dataclass
class SignalResult:
    """Standardized signal output from any strategy.

    Attributes:
        signal_type: One of "BUY", "SELL", or "HOLD".
        strength: Signal strength on a 0-100 scale.
        metadata: Strategy-specific context (e.g. z-score, RSI value).
    """

    signal_type: str
    strength: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParamSpec:
    """Parameter specification for UI rendering and validation.

    Attributes:
        label: Human-readable label (Chinese preferred for the frontend).
        type: One of "int", "float", "bool", or "choice".
        default: Default value used when the parameter is missing.
        min: Optional minimum value for numeric parameters.
        max: Optional maximum value for numeric parameters.
        options: Optional list of choices for "choice" type.
        description: Optional helper text shown in the UI.
        validators: Optional list of conditional validator descriptors
            (quant P2). Each validator is a dict, e.g.::

                {"when": {"name": "long_window"}, "op": "gt",
                 "other": "short_window"}

            meaning: "this param must be ``> long_window`` (relative to
            the param named ``short_window``)". The supported ``op``
            values are ``lt``, ``le``, ``eq``, ``ne``, ``ge``, ``gt``.
            The ``when`` clause scopes the validator to a sibling
            param by name (currently a no-op alias for ``other``,
            accepted so the schema can grow without a v2 break).
    """

    label: str
    type: str
    default: Any
    min: float | None = None
    max: float | None = None
    options: list[str] | None = None
    description: str = ""
    # Conditional validators (quant P2 — relative param relationships).
    # Each entry is a dict describing a relationship like
    # "self <op> <other_param>". Default is None / empty for full
    # backward compatibility with existing ParamSpec usage.
    validators: list[dict[str, Any]] | None = None


class Strategy(ABC):
    """Abstract base class for all trading strategies.

    Subclasses must define class-level metadata and implement
    ``generate`` (for the latest bar) and ``generate_series`` (for
    backtesting over a full history).
    """

    strategy_type: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str]
    family: ClassVar[str]
    param_specs: ClassVar[dict[str, ParamSpec]]
    min_bars: ClassVar[int] = 30

    def __init__(self, params: dict[str, Any] | None = None, db: Any = None):
        self.params = params or {}
        # Optional DB session for strategies that query event/fundamental
        # data (e.g. the event-driven strategy). Price-only strategies
        # ignore it. Typed as ``Any`` to avoid importing SQLAlchemy here.
        self.db = db
        self._validate_params()

    def _validate_params(self) -> None:
        """Validate params against ``param_specs`` and fill defaults.

        Performs three passes:

        1. Default-fill missing / ``None`` values from the spec.
        2. Clamp numeric params against ``min`` / ``max``.
        3. Enforce conditional validators (quant P2): the configured
           ``validators`` list on each spec is checked relative to the
           now-defaulted params. Validators whose ``other`` target is
           not a recognised param name are silently skipped (so the
           UI can preview a partially-built form without errors).
        """
        for key, spec in self.param_specs.items():
            if key not in self.params or self.params[key] is None:
                self.params[key] = spec.default

            value = self.params[key]
            if spec.type in ("int", "float"):
                if spec.min is not None and value < spec.min:
                    self.params[key] = spec.min
                if spec.max is not None and value > spec.max:
                    self.params[key] = spec.max

        # Conditional relative-parameter validators (quant P2).
        # These run AFTER default-fill so the comparison values reflect
        # the final params.
        _REL_OPS = {
            "lt": lambda a, b: a < b,
            "le": lambda a, b: a <= b,
            "eq": lambda a, b: a == b,
            "ne": lambda a, b: a != b,
            "ge": lambda a, b: a >= b,
            "gt": lambda a, b: a > b,
        }
        for key, spec in self.param_specs.items():
            validators = spec.validators or []
            for v in validators:
                op_name = v.get("op")
                if op_name not in _REL_OPS:
                    continue
                other_name = v.get("other")
                if not other_name or other_name not in self.params:
                    continue
                op = _REL_OPS[op_name]
                try:
                    ok = op(self.params[key], self.params[other_name])
                except TypeError:
                    # Incomparable types — skip rather than raise.
                    continue
                if not ok:
                    # Bump up so the relationship holds. For ``lt`` /
                    # ``le`` we set self = other - 1 (when both are
                    # numeric); for ``gt`` / ``ge`` we set self =
                    # other + 1; ``eq`` snaps to other; ``ne`` is left
                    # alone (don't try to "fix" an inequality).
                    self_value = self.params[key]
                    other_value = self.params[other_name]
                    if op_name in ("lt", "le"):
                        if isinstance(self_value, (int, float)) and isinstance(other_value, (int, float)):
                            self.params[key] = other_value - 1 if op_name == "lt" else other_value
                    elif op_name in ("gt", "ge"):
                        if isinstance(self_value, (int, float)) and isinstance(other_value, (int, float)):
                            self.params[key] = other_value + 1 if op_name == "gt" else other_value
                    elif op_name == "eq":
                        self.params[key] = other_value

    def bars_needed(self) -> int:
        """Return the minimum number of bars required by this strategy."""
        return self.min_bars

    @abstractmethod
    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        """Generate a signal for the latest bar in ``df``.

        Args:
            df: DataFrame with OHLCV columns sorted ascending by date.
                Guaranteed to contain at least ``bars_needed()`` rows.

        Returns:
            A ``SignalResult`` or ``None`` if no signal should be emitted.
        """
        raise NotImplementedError

    @abstractmethod
    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        """Generate a signal series for backtesting.

        Args:
            df: DataFrame with OHLCV columns sorted ascending by date.

        Returns:
            pandas Series of the same length as ``df`` with values
            ``1`` (BUY), ``-1`` (SELL), or ``0`` (HOLD).
        """
        raise NotImplementedError

    def _clamp_strength(self, value: float) -> int:
        """Clamp a raw strength value to the 0-100 range."""
        return int(max(0, min(100, value)))


class StrategyRegistry:
    """Central registry for all strategy classes."""

    _strategies: dict[str, type[Strategy]] = {}

    @classmethod
    def register(cls, strategy_class: type[Strategy]) -> type[Strategy]:
        """Decorator to register a strategy class."""
        cls._strategies[strategy_class.strategy_type] = strategy_class
        return strategy_class

    @classmethod
    def get(cls, strategy_type: str) -> type[Strategy] | None:
        """Get a strategy class by type identifier."""
        return cls._strategies.get(strategy_type)

    @classmethod
    def list_all(cls) -> list[dict[str, Any]]:
        """List all registered strategies with metadata."""
        return [
            {
                "strategy_type": s.strategy_type,
                "name": s.name,
                "description": s.description,
                "family": s.family,
                "param_specs": {
                    k: {
                        "label": v.label,
                        "type": v.type,
                        "default": v.default,
                        "min": v.min,
                        "max": v.max,
                        "options": v.options,
                        "description": v.description,
                    }
                    for k, v in s.param_specs.items()
                },
                "min_bars": s.min_bars,
            }
            for s in cls._strategies.values()
        ]

    @classmethod
    def list_by_family(cls, family: str) -> list[type[Strategy]]:
        """Get all registered strategies in a family."""
        return [s for s in cls._strategies.values() if s.family == family]

    @classmethod
    def families(cls) -> list[str]:
        """Get all unique family names."""
        return sorted({s.family for s in cls._strategies.values()})


def register_strategy(strategy_class: type[Strategy]) -> type[Strategy]:
    """Convenience decorator for registering strategies."""
    return StrategyRegistry.register(strategy_class)


# ---------------------------------------------------------------------------
# Generic composite strategy (quant P1)
# ---------------------------------------------------------------------------
#
# A first-class citizen in the registry so research notebooks and the
# new ``POST /backtests/composite`` endpoint can synthesise strategies
# out of any registered component strategy. The triple-screen style of
# hard-coded composite is still available under ``strategy_type="triple_screen"``;
# this is the **generic** version that takes an arbitrary list of
# components plus an aggregation rule.
#
# Aggregation rules:
#   - ``"weighted"``:   final signal = sum(weight_i * sign_i) where each
#     component contributes its signed ``generate_series`` output [-1, 0, 1]
#     multiplied by ``weight_i``. Then the final signal is mapped to
#     ``[-1, 0, 1]`` by sign(final_score). Empty / zero score -> HOLD.
#   - ``"vote"``:       final signal = majority vote. If the SIGNED sum
#     of component votes (``len(BUY) - len(SELL)``) is positive -> BUY,
#     negative -> SELL, zero -> HOLD. Ties (zero net votes) -> HOLD.
#   - ``"unanimous"``:  BUY only when EVERY component emits BUY; SELL
#     only when EVERY component emits SELL; otherwise HOLD.
#
# The ``metadata`` field on the emitted SignalResult carries per-component
# breakdowns so downstream consumers (UI, audit logs) can inspect the
# pipeline.


@register_strategy
class CompositeStrategy(Strategy):
    """Generic composite strategy.

    Compose any number of registered strategies into a single signal
    stream under one of three aggregation rules (``weighted`` /
    ``vote`` / ``unanimous``).

    params layout::

        {
            "components": [
                {"type": "momentum",         "params": {...}, "weight": 0.4},
                {"type": "mean_reversion",   "params": {...}, "weight": 0.3},
                {"type": "rsi",              "params": {...}, "weight": 0.3},
            ],
            "aggregation": "weighted",  # or "vote" / "unanimous"
            "holding_period": 20,
        }
    """

    strategy_type = "composite"
    name = "通用复合策略"
    description = "将多个策略按权重/投票/一致同意聚合"
    family = "composite"
    param_specs = {
        "aggregation": ParamSpec(
            label="聚合方式",
            type="choice",
            default="weighted",
            options=["weighted", "vote", "unanimous"],
            description="weighted=加权求和；vote=多数票；unanimous=一致同意",
        ),
        "holding_period": ParamSpec(
            label="持有周期",
            type="int",
            default=20,
            min=1,
            max=120,
        ),
    }

    def __init__(self, params: dict[str, Any] | None = None, db: Any = None):
        # Components are described as a list of dicts. We *do not* try
        # to express that as a single ParamSpec dict (the frontend
        # renders the component sub-form from the registry), but we
        # still want a defensive default so single-component composites
        # work out of the box.
        super().__init__(params or {}, db=db)
        if "components" not in self.params:
            self.params["components"] = [
                {"type": "momentum", "params": {"momentum_window": 20, "threshold": 0.05}, "weight": 0.5},
                {"type": "mean_reversion", "params": {"lookback_window": 20, "z_score_threshold": 2.0}, "weight": 0.5},
            ]

    def bars_needed(self) -> int:
        return max(
            (self.params.get("holding_period", 20) + 5),
            30,  # sanity floor
        )

    # ------------------------------------------------------------------
    # Core composite helpers
    # ------------------------------------------------------------------

    def _component_signals(self, df: pd.DataFrame) -> list[tuple[str, pd.Series]]:
        """Run every component and return ``[(type, signal_series), ...]``.

        Unknown strategies are silently skipped so a partial config
        (e.g. during iterative UI editing) doesn't crash the run.
        """
        out: list[tuple[str, pd.Series]] = []
        components = self.params.get("components") or []
        for comp in components:
            ctype = comp.get("type")
            cparams = comp.get("params") or {}
            cls = StrategyRegistry.get(ctype) if ctype else None
            if cls is None:
                continue
            try:
                series = cls(cparams, db=self.db).generate_series(df)
            except Exception:
                continue
            if not isinstance(series, pd.Series) or len(series) != len(df):
                continue
            out.append((ctype or "unknown", series.astype(int)))
        return out

    def _aggregate(
        self, components: list[tuple[str, pd.Series]]
    ) -> tuple[pd.Series, dict[str, Any]]:
        """Combine per-component signal Series into a single Series.

        Returns the final ``[-1, 0, 1]`` Series plus a metadata dict
        with the per-component weights / raw votes so the calling
        ``generate`` / ``generate_series`` can plumb them through to
        the SignalResult.
        """
        aggregation = self.params.get("aggregation", "weighted")
        per_bar: list[list[tuple[str, int, float]]] = []
        weights_by_type: dict[str, float] = {}
        weights = [
            float(comp.get("weight", 1.0))
            for comp in (self.params.get("components") or [])
            if StrategyRegistry.get(comp.get("type")) is not None
        ]
        for (ctype, _series), w in zip(components, weights):
            weights_by_type[ctype] = w
        # We capture (type, signal, weight) per bar for the strongest /
        # dissent components so generate() can expose them in metadata.
        for i in range(len(components[0][1]) if components else 0):
            row: list[tuple[str, int, float]] = []
            for (ctype, series), w in zip(components, weights):
                row.append((ctype, int(series.iloc[i]), w))
            per_bar.append(row)

        # Per-bar aggregation
        final: list[int] = []
        for row in per_bar:
            if aggregation == "unanimous":
                vals = [s for (_, s, _) in row]
                if all(v == 1 for v in vals):
                    final.append(1)
                elif all(v == -1 for v in vals):
                    final.append(-1)
                else:
                    final.append(0)
            elif aggregation == "vote":
                buys = sum(1 for (_, s, _) in row if s == 1)
                sells = sum(1 for (_, s, _) in row if s == -1)
                if buys > sells:
                    final.append(1)
                elif sells > buys:
                    final.append(-1)
                else:
                    final.append(0)
            else:
                # weighted (default)
                score = sum(float(s) * w for (_, s, w) in row)
                if score > 0:
                    final.append(1)
                elif score < 0:
                    final.append(-1)
                else:
                    final.append(0)

        idx = (
            components[0][1].index
            if components
            else pd.RangeIndex(0)
        )
        return pd.Series(final, index=idx, dtype=int), {
            "aggregation": aggregation,
            "weights": weights_by_type,
        }

    # ------------------------------------------------------------------
    # Strategy overrides
    # ------------------------------------------------------------------

    def generate(self, df: pd.DataFrame) -> SignalResult | None:
        components = self._component_signals(df)
        if not components:
            return None

        final_series, agg_meta = self._aggregate(components)
        if final_series.empty:
            return None
        last = int(final_series.iloc[-1])

        # Build a per-component snapshot of the *last* bar for metadata.
        per_comp_last: dict[str, dict[str, Any]] = {}
        for i, (ctype, series) in enumerate(components):
            weight = float(self.params.get("components", [{}])[i].get("weight", 1.0))
            per_comp_last[ctype] = {
                "signal": int(series.iloc[-1]),
                "weight": weight,
            }

        signal_type = "BUY" if last == 1 else "SELL" if last == -1 else "HOLD"
        # Strength scales with the number of agreeing components when
        # in vote / unanimous mode, or with the absolute weighted score
        # in weighted mode.
        if agg_meta["aggregation"] == "weighted":
            weighted_score = sum(
                v["signal"] * v["weight"] for v in per_comp_last.values()
            )
            strength = self._clamp_strength(abs(weighted_score) * 100)
        else:
            agreeing = sum(
                1 for v in per_comp_last.values()
                if v["signal"] == last
            )
            strength = self._clamp_strength(
                (agreeing / max(1, len(per_comp_last))) * 100
            )

        return SignalResult(
            signal_type=signal_type,
            strength=strength,
            metadata={
                "aggregation": agg_meta["aggregation"],
                "components": per_comp_last,
            },
        )

    def generate_series(self, df: pd.DataFrame) -> pd.Series:
        components = self._component_signals(df)
        if not components:
            return pd.Series(0, index=df.index)
        final_series, _meta = self._aggregate(components)
        return final_series
