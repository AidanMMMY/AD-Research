"""Statistics API routes for dashboard overview."""

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.etf import ETFIndicator, ETFInfo
from app.models.scoring import ETFScore, ScoreTemplate

router = APIRouter()


@router.get("/overview")
def get_overview(db: Session = Depends(get_db)):
    """Get dashboard overview statistics."""
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

    # Get latest trade date with indicators
    latest_date = db.query(func.max(ETFIndicator.trade_date)).scalar()

    # Get latest score date
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
