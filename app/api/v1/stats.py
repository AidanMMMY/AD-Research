"""Statistics API routes for dashboard overview."""

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_optional, get_db, require_admin
from app.models.etf import ETFIndicator, ETFInfo
from app.models.scoring import ETFScore, ScoreTemplate
from app.models.web_vitals import WebVitalsLog
from app.schemas.auth import UserResponse
from app.schemas.web_vitals import WebVitalsPayload

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# 60s 进程内 TTL 缓存（2026-08-05 P0 修复）。
#
# 事故背景：Dashboard 4 张 KPI 卡并行打 /overview/{metric}，旧实现每个
# metric 端点都跑 _collect_overview 全量 8 条 COUNT/MAX（含 etf_score
# 115 万行、etf_indicator 1613 万行的全表 COUNT），4 路并行 = 32 条重
# 查询互抢 DB，单请求 12-13s，浏览器/原生端全部超时 → 首页 KPI 永久
# 转圈。修复双管齐下：per-metric 只跑自己那一条 + 60s 缓存折叠并发。
# ---------------------------------------------------------------------------

_OVERVIEW_TTL_SECONDS = 60.0
_overview_cache: dict[str, tuple[float, object]] = {}
_overview_lock = threading.Lock()


def _cached(key: str, compute):
    now = time.monotonic()
    with _overview_lock:
        hit = _overview_cache.get(key)
        if hit is not None and now - hit[0] < _OVERVIEW_TTL_SECONDS:
            return hit[1]
    value = compute()
    with _overview_lock:
        _overview_cache[key] = (now, value)
    return value


def _collect_overview(db: Session) -> dict:
    """Compute all overview counters in one pass (60s cached).

    Frontend either hits ``/overview`` (single round-trip) or the
    per-metric ``/overview/{metric}`` endpoints so the 4 KPI cards can
    load in parallel and stream into the page as each becomes ready.
    """
    def _compute() -> dict:
        etf_count = db.query(func.count(ETFInfo.id)).scalar() or 0
        category_count = (
            db.query(func.count(func.distinct(ETFInfo.category)))
            .filter(ETFInfo.category.isnot(None))
            .scalar()
            or 0
        )
        market_count = (
            db.query(func.count(func.distinct(ETFInfo.market))).scalar() or 0
        )
        indicator_count = db.query(func.count(ETFIndicator.id)).scalar() or 0
        score_count = db.query(func.count(ETFScore.id)).scalar() or 0
        template_count = db.query(func.count(ScoreTemplate.id)).scalar() or 0

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

    return _cached("overview", _compute)


@router.get("/overview")
def get_overview(
    db: Session = Depends(get_db),
    _: UserResponse = Depends(get_current_user),
):
    """Get dashboard overview statistics (authenticated users only)."""
    return _collect_overview(db)


# ---------------------------------------------------------------------------
# Per-metric endpoints (Dashboard 4-card parallel loading, 2026-07-07).
# 2026-08-05 P0：每个端点只跑自己那一条 COUNT（旧版全部跑全量 8 条，
# 见顶部缓存注释），各带独立 60s 缓存键，4 路并发折叠为 4 条单查。
# ---------------------------------------------------------------------------


def _count_etf(db: Session) -> int:
    return db.query(func.count(ETFInfo.id)).scalar() or 0


def _count_score(db: Session) -> int:
    return db.query(func.count(ETFScore.id)).scalar() or 0


def _count_category(db: Session) -> int:
    return (
        db.query(func.count(func.distinct(ETFInfo.category)))
        .filter(ETFInfo.category.isnot(None))
        .scalar()
        or 0
    )


def _count_template(db: Session) -> int:
    return db.query(func.count(ScoreTemplate.id)).scalar() or 0


_METRIC_QUERIES = {
    "etf-count": _count_etf,
    "score-count": _count_score,
    "category-count": _count_category,
    "template-count": _count_template,
}


@router.get("/overview/{metric}")
def get_overview_metric(
    metric: str,
    db: Session = Depends(get_db),
    _: UserResponse = Depends(get_current_user),
):
    """Return a single dashboard counter.

    ``metric`` is one of: ``etf-count``, ``score-count``,
    ``category-count``, ``template-count``. Returns 404 for anything
    else so the frontend's React Query doesn't accidentally treat a
    typo as a valid empty response. Response shape is
    ``{"value": <number>}`` so the frontend can read a single key
    regardless of which metric was requested.
    """
    query_fn = _METRIC_QUERIES.get(metric)
    if query_fn is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"Unknown metric '{metric}'")
    value = _cached(f"metric:{metric}", lambda: query_fn(db))
    return {"value": value, "metric": metric}


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