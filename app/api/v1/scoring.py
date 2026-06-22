"""Scoring API routes.

Provides endpoints for score template management and ETF composite score queries.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_scoring_service
from app.schemas.scoring import (
    ETFScoreListResponse,
    ETFScoreResponse,
    ScoreTemplateCreate,
    ScoreTemplateResponse,
    ScoreTemplateUpdate,
)
from app.services.scoring_service import ScoringService

router = APIRouter()


# ------------------------------------------------------------------
# Template routes
# ------------------------------------------------------------------

@router.get("/templates", response_model=list[ScoreTemplateResponse])
def list_templates(service: ScoringService = Depends(get_scoring_service)):
    """List all score templates."""
    templates = service.get_templates()
    return templates


@router.post("/templates", response_model=ScoreTemplateResponse, status_code=201)
def create_template(
    data: ScoreTemplateCreate,
    service: ScoringService = Depends(get_scoring_service),
):
    """Create a new score template."""
    return service.create_template(
        name=data.name,
        description=data.description,
        weights=data.weights,
        is_default=data.is_default,
    )


@router.put("/templates/{template_id}", response_model=ScoreTemplateResponse)
def update_template(
    template_id: int,
    data: ScoreTemplateUpdate,
    service: ScoringService = Depends(get_scoring_service),
):
    """Update an existing score template."""
    template = service.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")

    if data.name is not None:
        template.name = data.name
    if data.description is not None:
        template.description = data.description
    if data.weights is not None:
        template.weights = data.weights
    if data.is_default is not None:
        template.is_default = data.is_default

    service.db.commit()
    service.db.refresh(template)
    return template


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(
    template_id: int,
    service: ScoringService = Depends(get_scoring_service),
):
    """Delete a score template (cannot delete the default template)."""
    template = service.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")

    if template.is_default:
        raise HTTPException(
            status_code=400, detail="Cannot delete the default template"
        )

    service.db.delete(template)
    service.db.commit()
    return None


# ------------------------------------------------------------------
# Score query routes
# ------------------------------------------------------------------

@router.get("", response_model=ETFScoreListResponse)
def list_scores(
    template_id: int | None = Query(None, description="Filter by template ID"),
    market: str | None = Query(None, description="Filter by market (e.g. SH, SZ)"),
    category: str | None = Query(None, description="Filter by ETF category"),
    trade_date: date | None = Query(None, description="Filter by trade date"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of results"),
    service: ScoringService = Depends(get_scoring_service),
):
    """List ETF composite scores with optional filtering.

    Results are ordered by overall rank (best first).
    """
    scores = service.get_scores(
        template_id=template_id,
        trade_date=trade_date,
        limit=limit,
        market=market,
        category=category,
    )

    # Resolve effective template_id for the response
    effective_template_id = template_id
    if effective_template_id is None:
        default = service.get_default_template()
        effective_template_id = default.id if default else 0

    # Resolve effective trade_date for the response
    effective_trade_date = trade_date
    if effective_trade_date is None:
        from sqlalchemy import func

        from app.models.scoring import ETFScore

        effective_trade_date = (
            service.db.query(func.max(ETFScore.trade_date))
            .filter(ETFScore.template_id == effective_template_id)
            .scalar()
        )

    return ETFScoreListResponse(
        items=scores,
        total=len(scores),
        template_id=effective_template_id,
        trade_date=effective_trade_date,
    )


@router.get("/{etf_code}", response_model=ETFScoreResponse)
def get_etf_score(
    etf_code: str,
    template_id: int | None = Query(None, description="Filter by template ID"),
    trade_date: date | None = Query(None, description="Filter by trade date"),
    service: ScoringService = Depends(get_scoring_service),
):
    """Get the composite score for a single ETF."""
    scores = service.get_scores(
        template_id=template_id,
        trade_date=trade_date,
        limit=1,
    )

    # Filter to the requested ETF code
    for score in scores:
        if score["etf_code"] == etf_code:
            return ETFScoreResponse(**score)

    # If not found in the default query, try a broader search
    from sqlalchemy import func

    from app.models.etf import ETFInfo
    from app.models.scoring import ETFScore

    query = (
        service.db.query(ETFScore, ETFInfo)
        .join(ETFInfo, ETFScore.etf_code == ETFInfo.code)
        .filter(ETFScore.etf_code == etf_code)
    )

    if template_id is not None:
        query = query.filter(ETFScore.template_id == template_id)
    if trade_date is not None:
        query = query.filter(ETFScore.trade_date == trade_date)
    else:
        # Get the latest available score for this ETF
        subq = (
            service.db.query(func.max(ETFScore.trade_date).label("latest_date"))
            .filter(ETFScore.etf_code == etf_code)
        )
        if template_id is not None:
            subq = subq.filter(ETFScore.template_id == template_id)
        latest_date = subq.scalar()
        if latest_date:
            query = query.filter(ETFScore.trade_date == latest_date)

    result = query.first()
    if not result:
        raise HTTPException(
            status_code=404, detail=f"No score found for ETF {etf_code}"
        )

    score, info = result
    return ETFScoreResponse(
        etf_code=score.etf_code,
        etf_name=info.name,
        market=info.market,
        category=info.category,
        trade_date=score.trade_date,
        composite_score=float(score.composite_score) if score.composite_score is not None else None,
        score_return=float(score.score_return) if score.score_return is not None else None,
        score_risk=float(score.score_risk) if score.score_risk is not None else None,
        score_sharpe=float(score.score_sharpe) if score.score_sharpe is not None else None,
        score_liquidity=float(score.score_liquidity) if score.score_liquidity is not None else None,
        score_trend=float(score.score_trend) if score.score_trend is not None else None,
        rank_overall=score.rank_overall,
        rank_category=score.rank_category,
    )
