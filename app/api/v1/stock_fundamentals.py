from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_stock_fundamental_service
from app.schemas.stock_fundamental import StockFundamentalResponse
from app.services.stock_fundamental_service import StockFundamentalService

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/{code}", response_model=StockFundamentalResponse)
def get_stock_fundamental(
    code: str,
    service: StockFundamentalService = Depends(get_stock_fundamental_service),
):
    """Get latest valuation and income data for an A-share stock.

    Returns PE(TTM), PB, market cap (CNY 万元), turnover rate,
    volume ratio, EPS, ROE, revenue YoY growth, and margin data.
    """
    result = service.get_latest(code)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Fundamental data not found for {code}")
    return result
