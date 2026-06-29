"""ETF screening and ranking API routes.

Provides endpoints for multi-condition ETF screening, preset-based screening,
and category enumeration with ETF counts.
"""


from fastapi import APIRouter, Depends, Query

from app.api.deps import get_screening_service
from app.schemas.screening import (
    CategoryListResponse,
    PresetListResponse,
    ScreenResult,
)
from app.services.screening_service import ScreeningService

router = APIRouter()


@router.get("", response_model=ScreenResult)
def screen_etfs(
    market: str | None = Query(None, description="Filter by market (e.g. SH, SZ)"),
    category: str | None = Query(None, description="Filter by ETF category"),
    rsi_min: float | None = Query(None, ge=0, le=100, description="Minimum RSI14"),
    rsi_max: float | None = Query(None, ge=0, le=100, description="Maximum RSI14"),
    sharpe_min: float | None = Query(None, description="Minimum Sharpe ratio (1y)"),
    sharpe_max: float | None = Query(None, description="Maximum Sharpe ratio (1y)"),
    volatility_min: float | None = Query(None, ge=0, description="Minimum 20d volatility"),
    volatility_max: float | None = Query(None, ge=0, description="Maximum 20d volatility"),
    return_1m_min: float | None = Query(None, description="Minimum 1-month return (%)"),
    return_1m_max: float | None = Query(None, description="Maximum 1-month return (%)"),
    return_3m_min: float | None = Query(None, description="Minimum 3-month return (%)"),
    return_3m_max: float | None = Query(None, description="Maximum 3-month return (%)"),
    return_1y_min: float | None = Query(None, description="Minimum 1-year return (%)"),
    return_1y_max: float | None = Query(None, description="Maximum 1-year return (%)"),
    max_drawdown_1y_min: float | None = Query(None, description="Minimum 1-year max drawdown (%)"),
    max_drawdown_1y_max: float | None = Query(None, description="Maximum 1-year max drawdown (%)"),
    score_min: float | None = Query(None, ge=0, le=100, description="Minimum composite score"),
    score_max: float | None = Query(None, ge=0, le=100, description="Maximum composite score"),
    template_id: int | None = Query(None, description="Score template ID"),
    sort_by: str = Query("composite_score", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=500, description="Pagination limit"),
    preset: str | None = Query(None, description="Use a preset (high_sharpe_low_vol, trend_strong, value_pit, liquidity_sufficient)"),
    service: ScreeningService = Depends(get_screening_service),
):
    """Screen ETFs with multiple filter conditions.

    Uses the latest available indicator data per ETF. Results can be sorted
    by any indicator or score field. If `preset` is provided, preset filters
    and sorting are applied instead of individual parameters.
    """
    if preset:
        return service.screen_by_preset(
            preset_key=preset,
            offset=offset,
            limit=limit,
        )

    return service.screen(
        market=market,
        category=category,
        rsi_min=rsi_min,
        rsi_max=rsi_max,
        sharpe_min=sharpe_min,
        sharpe_max=sharpe_max,
        volatility_min=volatility_min,
        volatility_max=volatility_max,
        return_1m_min=return_1m_min,
        return_1m_max=return_1m_max,
        return_3m_min=return_3m_min,
        return_3m_max=return_3m_max,
        return_1y_min=return_1y_min,
        return_1y_max=return_1y_max,
        max_drawdown_1y_min=max_drawdown_1y_min,
        max_drawdown_1y_max=max_drawdown_1y_max,
        score_min=score_min,
        score_max=score_max,
        template_id=template_id,
        sort_by=sort_by,
        sort_order=sort_order,
        offset=offset,
        limit=limit,
    )


@router.get("/presets", response_model=PresetListResponse)
def list_presets(
    service: ScreeningService = Depends(get_screening_service),
):
    """List all available screening presets."""
    presets = service.get_presets()
    return PresetListResponse(presets=presets)


@router.get("/categories", response_model=CategoryListResponse)
def list_categories(
    market: str = Query(None, description="Filter by market"),
    service: ScreeningService = Depends(get_screening_service),
):
    """List ETF categories with active ETF counts, optionally filtered by market."""
    categories = service.get_categories(market=market)
    return CategoryListResponse(categories=categories)
