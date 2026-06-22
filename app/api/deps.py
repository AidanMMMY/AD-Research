"""FastAPI dependency injection utilities.

Provides database session and service instance dependencies for all API routes.
"""

from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user
from app.core.database import SessionLocal
from app.services.analysis_service import AnalysisService
from app.services.attribution_service import AttributionService
from app.services.backtest_service import BacktestService
from app.services.etf_scanner_service import ETFScannerService
from app.services.etf_service import ETFService
from app.services.favorite_service import FavoriteService
from app.services.indicator_service import IndicatorService
from app.services.market_data_service import MarketDataService
from app.services.notification_service import NotificationService
from app.services.pool_enhancement_service import PoolEnhancementService
from app.services.pool_service import PoolService
from app.services.report_service import ReportService
from app.services.scoring_service import ScoringService
from app.services.screening_service import ScreeningService
from app.services.sector_rotation_service import SectorRotationService
from app.services.signal_service import SignalService
from app.services.strategy_comparison_service import StrategyComparisonService
from app.services.strategy_service import StrategyService

__all__ = [
    "get_current_user",
    "get_db",
    "get_etf_service",
    "get_pool_service",
    "get_market_data_service",
    "get_indicator_service",
    "get_analysis_service",
    "get_scoring_service",
    "get_screening_service",
    "get_pool_enhancement_service",
    "get_report_service",
    "get_sector_rotation_service",
    "get_etf_scanner_service",
    "get_notification_service",
    "get_strategy_service",
    "get_backtest_service",
    "get_signal_service",
    "get_attribution_service",
    "get_strategy_comparison_service",
    "get_favorite_service",
]


def get_db() -> Generator[Session, None, None]:
    """Yield a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_etf_service(db: Session = Depends(get_db)) -> ETFService:
    """Provide an ETFService instance with a DB session."""
    return ETFService(db)


def get_pool_service(db: Session = Depends(get_db)) -> PoolService:
    """Provide a PoolService instance with a DB session."""
    return PoolService(db)


def get_market_data_service(db: Session = Depends(get_db)) -> MarketDataService:
    """Provide a MarketDataService instance with a DB session."""
    return MarketDataService(db)


def get_indicator_service(db: Session = Depends(get_db)) -> IndicatorService:
    """Provide an IndicatorService instance with a DB session."""
    return IndicatorService(db)


def get_analysis_service(db: Session = Depends(get_db)) -> AnalysisService:
    """Provide an AnalysisService instance with a DB session."""
    return AnalysisService(db)


def get_scoring_service(db: Session = Depends(get_db)) -> ScoringService:
    """Provide a ScoringService instance with a DB session."""
    return ScoringService(db)


def get_screening_service(db: Session = Depends(get_db)) -> ScreeningService:
    """Provide a ScreeningService instance with a DB session."""
    return ScreeningService(db)


def get_pool_enhancement_service(db: Session = Depends(get_db)) -> PoolEnhancementService:
    """Provide a PoolEnhancementService instance with a DB session."""
    return PoolEnhancementService(db)


def get_report_service(db: Session = Depends(get_db)) -> ReportService:
    """Provide a ReportService instance with a DB session."""
    return ReportService(db)


def get_sector_rotation_service(db: Session = Depends(get_db)) -> SectorRotationService:
    """Provide a SectorRotationService instance with a DB session."""
    return SectorRotationService(db)


def get_etf_scanner_service(db: Session = Depends(get_db)) -> ETFScannerService:
    """Provide an ETFScannerService instance with a DB session."""
    return ETFScannerService(db)


def get_notification_service(db: Session = Depends(get_db)) -> NotificationService:
    """Provide a NotificationService instance with a DB session."""
    return NotificationService(db)


def get_strategy_service(db: Session = Depends(get_db)) -> StrategyService:
    """Provide a StrategyService instance with a DB session."""
    return StrategyService(db)


def get_backtest_service(db: Session = Depends(get_db)) -> BacktestService:
    """Provide a BacktestService instance with a DB session."""
    return BacktestService(db)


def get_signal_service(db: Session = Depends(get_db)) -> SignalService:
    """Provide a SignalService instance with a DB session."""
    return SignalService(db)


def get_attribution_service(db: Session = Depends(get_db)) -> AttributionService:
    """Provide an AttributionService instance with a DB session."""
    return AttributionService(db)


def get_strategy_comparison_service(db: Session = Depends(get_db)) -> StrategyComparisonService:
    """Provide a StrategyComparisonService instance with a DB session."""
    return StrategyComparisonService(db)


def get_favorite_service(db: Session = Depends(get_db)) -> FavoriteService:
    """Provide a FavoriteService instance with a DB session."""
    return FavoriteService(db)
