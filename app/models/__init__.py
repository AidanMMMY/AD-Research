"""ORM models package.

Re-exports all model classes for convenient imports.
"""

from app.models.etf import ETFInfo, ETFDailyBar, ETFIndicator, FXRate
from app.models.etl import DataSourceConfig, ETLLog, StrategyConfig, BacktestResult, Signal
from app.models.pool import ETFPools, PoolMember, PoolWeight, PoolSnapshot
from app.models.scoring import ScoreTemplate, ETFScore, ReportMetadata

__all__ = [
    # ETF models
    "ETFInfo",
    "ETFDailyBar",
    "ETFIndicator",
    "FXRate",
    # Pool models
    "ETFPools",
    "PoolMember",
    "PoolWeight",
    "PoolSnapshot",
    # Scoring models
    "ScoreTemplate",
    "ETFScore",
    "ReportMetadata",
    # ETL / Strategy models
    "DataSourceConfig",
    "ETLLog",
    "StrategyConfig",
    "BacktestResult",
    "Signal",
]
