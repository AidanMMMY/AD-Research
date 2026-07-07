"""Statistics API routes for dashboard overview."""

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.etf import ETFIndicator, ETFInfo
from app.models.scoring import ETFScore, ScoreTemplate

router = APIRouter()


def _collect_overview(db: Session) -> dict:
    """Compute all overview counters in one pass.

    Frontend either hits ``/overview`` (single round-trip) or the
    per-metric ``/overview/{metric}`` endpoints so the 4 KPI cards can
    load in parallel and stream into the page as each becomes ready.
    """
    etf_count = db.query(ETFInfo).count()
    category_count = (
        db.query(ETFInfo.category)
        .filter(ETFInfo.category.isnot(None))
        .distinct()
        .count()
    )
    market_count = db.query(ETFInfo.market).distinct().count()
    indicator_count = db.query(ETFIndicator).count()
    score_count = db.query(ETFScore).count()
    template_count = db.query(ScoreTemplate).count()

    latest_date = db.query(func.max(ETFIndicator.trade_date)).scalar()
    latest_score_date = db.query(func.max(ETFScore.trade_date)).scalar()

    return {
        "etf_count": etf_count,
        "category_count": category_count,
        "market_count": market_count,
        "indicator_count": indicator_count,
        "score_count": score_count,
        "template_count": template_count,
        "latest_indicator_date": latest_date.isoformat() if latest_date else None,
        "latest_score_date": latest_score_date.isoformat() if latest_score_date else None,
    }


@router.get("/overview")
def get_overview(db: Session = Depends(get_db)):
    """Get dashboard overview statistics."""
    return _collect_overview(db)


# ---------------------------------------------------------------------------
# Per-metric endpoints (Dashboard 4-card parallel loading, 2026-07-07).
# Each route runs the same COUNT / MAX query as the bundled /overview
# endpoint but only returns a single field. The frontend fires all 4
# queries in parallel and renders each card as soon as its data lands,
# so the first paint isn't blocked by the slowest count.
# ---------------------------------------------------------------------------

_METRIC_FIELDS = {
    "etf-count": ("etf_count",),
    "score-count": ("score_count",),
    "category-count": ("category_count",),
    "template-count": ("template_count",),
}


@router.get("/overview/{metric}")
def get_overview_metric(metric: str, db: Session = Depends(get_db)):
    """Return a single dashboard counter.

    ``metric`` is one of: ``etf-count``, ``score-count``,
    ``category-count``, ``template-count``. Returns 404 for anything
    else so the frontend's React Query doesn't accidentally treat a
    typo as a valid empty response. Response shape is
    ``{"value": <number>}`` so the frontend can read a single key
    regardless of which metric was requested.
    """
    fields = _METRIC_FIELDS.get(metric)
    if not fields:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"Unknown metric '{metric}'")
    overview = _collect_overview(db)
    return {"value": overview[fields[0]], "metric": metric}
