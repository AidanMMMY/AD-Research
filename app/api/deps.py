"""FastAPI dependency injection utilities.

Provides database session, service instance, and auth dependencies for all API routes.
"""

import contextvars
from collections.abc import Generator

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import auth_settings
from app.core.database import SessionLocal
from app.core.redis_client import is_token_blacklisted
from app.models.user import User
from app.schemas.auth import UserResponse

# Context variable to expose the current request's jti (for logout blacklist)
_current_jti: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_current_jti", default=None
)
from app.services.analysis_service import AnalysisService
from app.services.attribution_service import AttributionService
from app.services.backtest_service import BacktestService
from app.services.cninfo_report_service import CninfoReportService
from app.services.etf_scanner_service import ETFScannerService
from app.services.etf_service import ETFService
from app.services.favorite_service import FavoriteService
from app.services.indicator_service import IndicatorService
from app.services.listing_event_service import ListingEventService
from app.services.market_data_service import MarketDataService
from app.services.notification_service import NotificationService
from app.services.paper_trading_service import PaperTradingService
from app.services.pool_enhancement_service import PoolEnhancementService
from app.services.pool_service import PoolService
from app.services.report_service import ReportService
from app.services.research_report_service import ResearchReportService
from app.services.risk_analysis_service import RiskAnalysisService
from app.services.scoring_service import ScoringService
from app.services.screening_service import ScreeningService
from app.services.sector_rotation_service import SectorRotationService
from app.services.signal_service import SignalService
from app.services.stock_fundamental_service import StockFundamentalService
from app.services.strategy_comparison_service import StrategyComparisonService
from app.services.strategy_service import StrategyService

__all__ = [
    "_current_jti",
    "get_current_user",
    "get_db",
    "require_admin",
    "get_etf_service",
    "get_pool_service",
    "get_market_data_service",
    "get_indicator_service",
    "get_analysis_service",
    "get_scoring_service",
    "get_screening_service",
    "get_pool_enhancement_service",
    "get_report_service",
    "get_risk_analysis_service",
    "get_sector_rotation_service",
    "get_etf_scanner_service",
    "get_notification_service",
    "get_strategy_service",
    "get_backtest_service",
    "get_cninfo_report_service",
    "get_signal_service",
    "get_attribution_service",
    "get_strategy_comparison_service",
    "get_favorite_service",
    "get_paper_trading_service",
    "get_stock_fundamental_service",
    "get_listing_event_service",
    "get_research_report_service",
]


security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserResponse:
    """Validate JWT, check Redis blacklist, and return the current user.

    Also sets _current_jti for use by the logout endpoint.
    """
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            auth_settings.SECRET_KEY,
            algorithms=["HS256"],
        )
        username: str | None = payload.get("sub")
        jti: str | None = payload.get("jti")

        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError as err:
        raise HTTPException(status_code=401, detail="Invalid token") from err

    # Check token revocation (Redis blacklist)
    if jti and is_token_blacklisted(jti):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    # Expose jti for logout
    _current_jti.set(jti)

    db = SessionLocal()
    try:
        from app.models.user import User

        user = db.query(User).filter(User.username == username).first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid or inactive user")
        return UserResponse(id=user.id, username=user.username, role=user.role)
    finally:
        db.close()


def require_admin(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """Dependency that enforces admin role."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def count_active_admins(db: Session) -> int:
    """Return the number of active admin users in the system.

    Used by ``admin_users`` write paths to enforce "at least one active
    admin must remain" (last-admin protection).
    """
    return (
        db.query(User)
        .filter(User.role == "admin", User.is_active.is_(True))
        .count()
    )


def assert_would_keep_at_least_one_admin(
    db: Session,
    *,
    target_user_id: int,
    new_role: str | None = None,
    new_is_active: bool | None = None,
) -> None:
    """Block an admin write that would orphan the system of admins.

    Raises 409 if the proposed change would leave zero active admins.
    ``new_role`` / ``new_is_active`` describe the *intended* state of
    the target row BEFORE the write is committed — pass ``None`` to
    leave that field unchanged.
    """
    target = db.query(User).filter(User.id == target_user_id).first()
    if not target:
        return  # not-found will be surfaced by the caller

    effective_role = new_role if new_role is not None else target.role
    effective_active = new_is_active if new_is_active is not None else target.is_active

    # Demoting/deactivating an admin only matters when the target is
    # currently an active admin.
    currently_admin = target.role == "admin" and target.is_active
    will_still_be_admin = effective_role == "admin" and effective_active
    if currently_admin and not will_still_be_admin:
        active_admin_count = count_active_admins(db)
        if active_admin_count <= 1:
            raise HTTPException(
                status_code=409,
                detail="At least one active admin must remain",
            )


def get_current_user_optional(request) -> UserResponse | None:
    """Optionally authenticate the user — returns None if no/invalid token.

    Used by SSE streams and public endpoints that optionally scope data.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header.removeprefix("Bearer ")
    try:
        payload = jwt.decode(token, auth_settings.SECRET_KEY, algorithms=["HS256"])
        username = payload.get("sub")
        jti = payload.get("jti")
        if not username:
            return None
        if jti and is_token_blacklisted(jti):
            return None
    except JWTError:
        return None

    db = SessionLocal()
    try:
        from app.models.user import User

        user = db.query(User).filter(User.username == username).first()
        if not user or not user.is_active:
            return None
        return UserResponse(id=user.id, username=user.username, role=user.role)
    finally:
        db.close()


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


def get_cninfo_report_service(db: Session = Depends(get_db)) -> CninfoReportService:
    """Provide a CninfoReportService instance with a DB session."""
    return CninfoReportService(db)


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


def get_paper_trading_service(db: Session = Depends(get_db)) -> PaperTradingService:
    """Provide a PaperTradingService instance with a DB session."""
    return PaperTradingService(db)


def get_stock_fundamental_service(db: Session = Depends(get_db)) -> StockFundamentalService:
    """Provide a StockFundamentalService instance with a DB session."""
    return StockFundamentalService(db)


def get_risk_analysis_service(db: Session = Depends(get_db)) -> RiskAnalysisService:
    """Provide a RiskAnalysisService instance with a DB session."""
    return RiskAnalysisService(db)


def get_listing_event_service(db: Session = Depends(get_db)) -> ListingEventService:
    """Provide a ListingEventService instance with a DB session."""
    return ListingEventService(db)


def get_research_report_service(db: Session = Depends(get_db)) -> ResearchReportService:
    """Provide a ResearchReportService instance with a DB session."""
    return ResearchReportService(db)
