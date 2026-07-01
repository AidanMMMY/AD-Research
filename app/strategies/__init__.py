"""Strategy package.

Importing this module registers all built-in strategy classes with the
``StrategyRegistry``. The registry is then used by the signal engine,
backtest engine, and API catalog endpoints.
"""

from app.strategies.base import (
    ParamSpec,
    SignalResult,
    Strategy,
    StrategyRegistry,
    register_strategy,
)
from app.strategies.composite import TripleScreenStrategy
from app.strategies.cross_sectional import MomentumRankStrategy
from app.strategies.event import EventDrivenStrategy
from app.strategies.mean_reversion import (
    BBMeanReversionStrategy,
    LegacyMeanReversionStrategy,
    LegacyRSIStrategy,
    RSIMeanReversionStrategy,
    ZScoreReversionStrategy,
)
from app.strategies.momentum import (
    LegacyMomentumStrategy,
    MTFMomentumStrategy,
    PriceMomentumStrategy,
    RateOfChangeStrategy,
)
from app.strategies.trend_following import (
    DonchianBreakoutStrategy,
    MACDStrategy,
    MACrossoverStrategy,
)
from app.strategies.volatility import (
    ATRTrailingStopStrategy,
    VolatilityBreakoutStrategy,
)
from app.strategies.volume import OBVTrendStrategy, VolumeBreakoutStrategy

__all__ = [
    "Strategy",
    "SignalResult",
    "ParamSpec",
    "register_strategy",
    "StrategyRegistry",
    "LegacyMomentumStrategy",
    "LegacyMeanReversionStrategy",
    "LegacyRSIStrategy",
    "MACrossoverStrategy",
    "MACDStrategy",
    "DonchianBreakoutStrategy",
    "RSIMeanReversionStrategy",
    "BBMeanReversionStrategy",
    "ZScoreReversionStrategy",
    "PriceMomentumStrategy",
    "MTFMomentumStrategy",
    "RateOfChangeStrategy",
    "ATRTrailingStopStrategy",
    "VolatilityBreakoutStrategy",
    "VolumeBreakoutStrategy",
    "OBVTrendStrategy",
    "TripleScreenStrategy",
    "MomentumRankStrategy",
    "EventDrivenStrategy",
]
