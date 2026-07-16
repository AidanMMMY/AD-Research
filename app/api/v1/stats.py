"""Statistics API routes for dashboard overview."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional, get_db, require_admin
from app.models.etf import ETFIndicator, ETFInfo
from app.models.scoring import ETFScore, ScoreTemplate
from app.models.web_vitals import WebVitalsLog
from app.schemas.auth import UserResponse
from app.schemas.web_vitals import WebVitalsPayload

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# Web Vitals ingestion (frontend perf telemetry, 2026-07-16).
#
# POST /api/v1/stats/web-vitals        — best-effort write, 204 on failure
# GET  /api/v1/stats/web-vitals/summary — admin: 24h p50/p75/p95 + rating
#                                         counts per metric
#
# Design notes:
# * The frontend uses navigator.sendBeacon so we MUST respond quickly
#   even when the DB is slow. The endpoint swallows all DB errors and
#   returns 204 — the client never retries, and a missed sample is
#   far cheaper than a blocked user navigation.
# * ``get_current_user_optional`` is called as a helper (not via
#   ``Depends``) because it expects a raw ``request`` object.
# ---------------------------------------------------------------------------


def _resolve_user_id(request: Request) -> int | None:
    """Best-effort user-id extraction from the Bearer token.

    Returns ``None`` if the token is missing or invalid — the endpoint
    remains anonymous-friendly so first-paint samples from logged-out
    visitors are still captured.
    """
    user: UserResponse | None = get_current_user_optional(request)
    return user.id if user else None


@router.post("/web-vitals", status_code=status.HTTP_200_OK)
def ingest_web_vital(
    payload: WebVitalsPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    """Persist one Core Web Vitals observation.

    Always returns ``{"ok": true}`` (200) on a successful write, or
    ``204 No Content`` if the DB layer raised anything. The 204 path
    still has a JSON body of ``{"ok": false}`` so the frontend's
    ``fetch(keepalive: true)`` wrapper can log a quiet warning.
    """
    user_id = _resolve_user_id(request)
    try:
        row = WebVitalsLog(
            name=payload.name,
            value=float(payload.value),
            rating=payload.rating,
            page=payload.page,
            navigation_type=payload.navigationType,
            vitals_id=payload.id,
            user_id=user_id,
        )
        db.add(row)
        db.commit()
    except Exception as exc:  # noqa: BLE001 — best-effort, swallow all
        db.rollback()
        logger.warning(
            "[web-vitals] ingest failed (name=%s): %s",
            payload.name,
            exc,
        )
        return Response(
            content='{"ok": false}',
            status_code=status.HTTP_204_NO_CONTENT,
            media_type="application/json",
        )
    return {"ok": True}


@router.get("/web-vitals/summary")
def web_vitals_summary(
    db: Session = Depends(get_db),
    _admin: UserResponse = Depends(require_admin),
):
    """24h aggregate: per-metric p50/p75/p95 + rating counts.

    Used by the perf badge / admin dashboards. We compute percentiles
    in Python (``numpy`` would be cheaper, but adding it just for this
    endpoint isn't worth it) because the row count over 24h is bounded
    by real-user volume — typically a few thousand rows at most.

    Returns ``{"window_hours": 24, "metrics": [...]}`` where each metric
    entry has ``name``, ``count``, ``p50``, ``p75``, ``p95`` and
    ``ratings`` (good/needs-improvement/poor counts).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    rows = (
        db.query(
            WebVitalsLog.name,
            WebVitalsLog.value,
            WebVitalsLog.rating,
        )
        .filter(WebVitalsLog.received_at >= cutoff)
        .all()
    )

    # Group in-process; sorted list lets us use bisect for percentiles
    # without dragging numpy into the dependency tree.
    grouped: dict[str, dict] = {}
    for name, value, rating in rows:
        bucket = grouped.setdefault(
            name,
            {"values": [], "ratings": {"good": 0, "needs-improvement": 0, "poor": 0}},
        )
        bucket["values"].append(float(value))
        # Tolerate unknown rating buckets so future web-vitals versions
        # don't crash the summary endpoint.
        bucket["ratings"][rating] = bucket["ratings"].get(rating, 0) + 1

    def _percentile(sorted_values: list[float], pct: float) -> float | None:
        if not sorted_values:
            return None
        if len(sorted_values) == 1:
            return sorted_values[0]
        # Linear interpolation between closest ranks (numpy default).
        k = (len(sorted_values) - 1) * pct
        lo = int(k)
        hi = min(lo + 1, len(sorted_values) - 1)
        frac = k - lo
        return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac

    metrics = []
    for name in sorted(grouped):
        bucket = grouped[name]
        values_sorted = sorted(bucket["values"])
        count = len(values_sorted)
        metrics.append(
            {
                "name": name,
                "count": count,
                "p50": _percentile(values_sorted, 0.50),
                "p75": _percentile(values_sorted, 0.75),
                "p95": _percentile(values_sorted, 0.95),
                "ratings": bucket["ratings"],
            }
        )

    return {
        "window_hours": 24,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
    }