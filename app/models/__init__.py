"""ORM models package.

Re-exports all model classes for convenient imports.
"""

from app.models.etf import ETFDailyBar, ETFIndicator, ETFInfo, FXRate
from app.models.etl import BacktestResult, DataSourceConfig, ETLLog, Signal, StrategyConfig
from app.models.pool import ETFPools, PoolMember, PoolSnapshot, PoolWeight
from app.models.scoring import ETFScore, ReportMetadata, ScoreTemplate
from app.models.user import User

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
    # User model
    "User",
    # ETL / Strategy models
    "DataSourceConfig",
    "ETLLog",
    "StrategyConfig",
    "BacktestResult",
    "Signal",
]
