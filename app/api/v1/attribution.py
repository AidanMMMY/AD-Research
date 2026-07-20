"""Attribution API routes."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_attribution_service, get_current_user
from app.schemas.attribution import AttributionResponse
from app.services.attribution_service import AttributionService

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/attribution/{backtest_id}", response_model=AttributionResponse)
def get_attribution(
    backtest_id: int,
    service: AttributionService = Depends(get_attribution_service),
):
    """Get performance attribution for a backtest."""
    result = service.analyze_backtest(backtest_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
