"""Analysis tools API routes.

Provides endpoints for correlation analysis, ranking, and ETF screening.
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_analysis_service, get_current_user, get_risk_analysis_service
from app.services.analysis_service import AnalysisService
from app.services.risk_analysis_service import RiskAnalysisService

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/correlation")
def get_correlation(
    codes: list[str] = Query(...),
    window: int = Query(60, ge=10, le=252),
    method: Literal["pearson", "spearman"] = Query("pearson"),
    service: AnalysisService = Depends(get_analysis_service),
):
    """Compute the return correlation matrix for a list of ETFs."""
    return service.correlation_matrix(codes, window=window, method=method)


@router.get("/ranking")
def get_ranking(
    sort_by: str = Query("sharpe_1y"),
    order: Literal["asc", "desc"] = Query("desc"),
    limit: int = Query(20, ge=1, le=100),
    market: str | None = Query(None),
    service: AnalysisService = Depends(get_analysis_service),
):
    """Rank ETFs by a specific indicator field."""
    return {"items": service.ranking(sort_by=sort_by, order=order, limit=limit, market=market)}


@router.get("/screen")
def get_screen(
    market: str | None = Query(None),
    category: str | None = Query(None),
    rsi_min: float | None = Query(None),
    rsi_max: float | None = Query(None),
    sharpe_min: float | None = Query(None),
    volatility_max: float | None = Query(None),
    service: AnalysisService = Depends(get_analysis_service),
):
    """Screen ETFs based on indicator criteria."""
    results = service.screen(
        market=market,
        category=category,
        rsi_min=rsi_min,
        rsi_max=rsi_max,
        sharpe_min=sharpe_min,
        volatility_max=volatility_max,
    )
    return {"items": results, "count": len(results)}


@router.get("/risk/instrument")
def get_instrument_risk(
    code: str = Query(..., description="Instrument code, e.g. 510300.SH"),
    window: int = Query(252, ge=30, le=756),
    end_date: date | None = Query(None),
    confidence: float = Query(0.95, ge=0.8, le=0.999),
    service: RiskAnalysisService = Depends(get_risk_analysis_service),
):
    """Compute risk metrics (volatility, VaR, ES, max drawdown) for a single instrument."""
    return service.analyze_instrument(code, window=window, end_date=end_date, confidence=confidence)


@router.get("/risk/portfolio")
def get_portfolio_risk(
    codes: list[str] = Query(..., description="Portfolio instrument codes"),
    weights: list[float] | None = Query(None, description="Optional weights; equal weight if omitted"),
    window: int = Query(252, ge=30, le=756),
    end_date: date | None = Query(None),
    confidence: float = Query(0.95, ge=0.8, le=0.999),
    service: RiskAnalysisService = Depends(get_risk_analysis_service),
):
    """Compute portfolio-level risk metrics and volatility contribution per instrument."""
    return service.analyze_portfolio(
        codes=codes,
        weights=weights,
        window=window,
        end_date=end_date,
        confidence=confidence,
    )
