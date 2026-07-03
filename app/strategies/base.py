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
    """

    label: str
    type: str
    default: Any
    min: float | None = None
    max: float | None = None
    options: list[str] | None = None
    description: str = ""


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
        """Validate params against ``param_specs`` and fill defaults."""
        for key, spec in self.param_specs.items():
            if key not in self.params or self.params[key] is None:
                self.params[key] = spec.default

            value = self.params[key]
            if spec.type in ("int", "float"):
                if spec.min is not None and value < spec.min:
                    self.params[key] = spec.min
                if spec.max is not None and value > spec.max:
                    self.params[key] = spec.max

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
