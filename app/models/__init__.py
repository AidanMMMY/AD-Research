"""ORM models package.

Re-exports all model classes for convenient imports.
"""

from app.models.cninfo_report import CninfoReport
from app.models.etf import (
    InstrumentDailyBar,
    ETFIndicator,
    ETFInfo,
    FXRate,
    StockBalanceSheet,
    StockFundamental,
    StockIncome,
)
from app.models.etl import BacktestResult, DataSourceConfig, ETLLog, Signal, StrategyConfig
from app.models.listing import ListingEvent
from app.models.macro import MacroIndicator
from app.models.microstructure import (
    HsgtFlow,
    LhbRecord,
    MarginBalance,
    RestrictedRelease,
)
from app.models.research_report import ResearchReport
from app.models.news import XueqiuFetchState, XueqiuUserCache
from app.models.pool import ETFPools, PoolMember, PoolSnapshot, PoolWeight
from app.models.scoring import ETFScore, ReportMetadata, ScoreTemplate
from app.models.trading import (
    LiveTradeConfig,
    LiveTradeOrder,
    LiveTradePosition,
    PaperTradeAccount,
    PaperTradeOrder,
    PaperTradePosition,
    RiskRule,
)
from app.models.user import User

__all__ = [
    # ETF models
    "ETFInfo",
    "InstrumentDailyBar",
    "ETFIndicator",
    "FXRate",
    # A-Share stock models
    "StockFundamental",
    "StockIncome",
    "StockBalanceSheet",
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
    # Trading models
    "PaperTradeAccount",
    "PaperTradeOrder",
    "PaperTradePosition",
    "LiveTradeConfig",
    "LiveTradeOrder",
    "LiveTradePosition",
    "RiskRule",
    # News / Xueqiu
    "XueqiuUserCache",
    "XueqiuFetchState",
    # Listing / IPO events
    "ListingEvent",
    # Macro indicators
    "MacroIndicator",
    # Micro-structure (LHB / HSGT / margin / restricted-release)
    "LhbRecord",
    "HsgtFlow",
    "MarginBalance",
    "RestrictedRelease",
    # Research reports (Eastmoney)
    "ResearchReport",
    # Cninfo (巨潮资讯) periodic reports
    "CninfoReport",
]
