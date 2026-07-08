"""ETF top-10 holdings coverage / stats service.

Single source of truth for the numbers surfaced by
``app.api.v1.etf_holdings_stats`` and the post-ETL coverage alert in
``app.scheduler_jobs.etf_holdings_quarterly``.

The metrics we compute:

* ``etf_count``         — distinct ETFs landed for the snapshot.
* ``eligible_etf_count``— total active A-share ETFs minus the
  ``etf_holding_unavailable`` blacklist (i.e. the ones the ETL was
  *expected* to land).
* ``coverage_pct``      — ``etf_count / eligible_etf_count`` × 100.
* ``days_ago``          — ``today - snapshot_date`` (Asia/Shanghai
  time). Negative when the snapshot is in the future (data entry
  error).
* ``unavailable_count`` — size of the blacklist for transparency.

The "denominator" is ``eligible_etf_count`` rather than the raw
``active A-share ETF count`` so the coverage KPI can reach 100% when
the ETL works correctly — otherwise the currency and gold ETFs would
artificially cap the metric.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import distinct, func, select, text
from sqlalchemy.orm import Session

from app.models.etf import ETFHolding, ETFHoldingUnavailable, ETFInfo


# ---------------------------------------------------------------------------
# Tunables — coverage alert thresholds.
# ---------------------------------------------------------------------------
# Each entry is ``(days_since_quarter_end, min_coverage_pct, severity)``.
# The scheduler job emits a WARN log when the *current* coverage for
# the most recent snapshot drops below any of these bands.  The
# defaults follow the revised AD-Research operational SLO (2026-07):
#  * 7 days after quarter end  → 60 % coverage expected (WARN)
#  * 14 days                   → 80 % coverage expected (WARN)
#  * 30 days                   → 90 % coverage expected (ERROR)
# Tweak ``COVERAGE_THRESHOLDS`` in this module to change the alert
# behaviour without touching the scheduler.
COVERAGE_THRESHOLDS: list[tuple[int, float, str]] = [
    (7, 60.0, "WARN"),
    (14, 80.0, "WARN"),
    (30, 90.0, "ERROR"),
]


@dataclass
class SnapshotCoverage:
    """Coverage summary for a single ``snapshot_date``."""

    snapshot_date: date
    etf_count: int
    row_count: int
    source_count: int
    sources: list[str]
    days_ago: int
    eligible_etf_count: int
    coverage_pct: float
    coverage_alerts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_date": self.snapshot_date.isoformat(),
            "etf_count": self.etf_count,
            "row_count": self.row_count,
            "source_count": self.source_count,
            "sources": self.sources,
            "days_ago": self.days_ago,
            "eligible_etf_count": self.eligible_etf_count,
            "coverage_pct": round(self.coverage_pct, 2),
            "coverage_alerts": self.coverage_alerts,
        }


def _eligible_etf_count(db: Session) -> int:
    """Count of active A-share ETFs minus the structurally-unavailable ones."""
    total = (
        db.query(func.count(distinct(ETFInfo.code)))
        .filter(
            ETFInfo.market == "A股",
            ETFInfo.instrument_type == "ETF",
            ETFInfo.status == "active",
        )
        .scalar()
        or 0
    )
    black = db.query(func.count(ETFHoldingUnavailable.etf_code)).scalar() or 0
    return max(total - black, 0)


def _compute_alerts(days_ago: int, coverage_pct: float) -> list[dict[str, Any]]:
    """Return the list of SLO breaches for the given snapshot.

    Only thresholds whose ``days_since_quarter_end`` is satisfied by
    the current ``days_ago`` are checked — a snapshot that landed
    yesterday is not subject to the 7-day SLO yet.  ``days_ago`` is
    clamped to 0 so future-dated snapshots never raise alerts (which
    would just be a clock skew issue, not a data problem).
    """
    elapsed = max(days_ago, 0)
    breached: list[dict[str, Any]] = []
    for threshold_days, min_pct, severity in COVERAGE_THRESHOLDS:
        if elapsed < threshold_days:
            continue
        if coverage_pct < min_pct:
            breached.append(
                {
                    "threshold_days": threshold_days,
                    "min_coverage_pct": min_pct,
                    "actual_coverage_pct": round(coverage_pct, 2),
                    "severity": severity,
                }
            )
    return breached


def list_snapshot_stats(db: Session) -> list[SnapshotCoverage]:
    """Return one ``SnapshotCoverage`` per distinct ``snapshot_date``.

    Reads from the ``etf_holding_stats`` view when available (Postgres
    production) and falls back to a direct aggregation otherwise
    (SQLite tests).  The two code paths produce the same shape so
    callers never need to special-case the database.
    """
    eligible = _eligible_etf_count(db)
    today = date.today()
    rows: list[SnapshotCoverage] = []

    bind = db.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        # Read the view (created in the b5e2c8f4a1d3 migration).  We
        # only fall through to the cross-dialect aggregation when the
        # view is *missing* — an empty result set is a valid answer
        # ("the ETL has not landed any rows yet") and should not
        # trigger the SQLite path on Postgres.
        view_missing = False
        try:
            raw = db.execute(
                text(
                    "SELECT snapshot_date, etf_count, row_count, "
                    "source_count, sources, days_ago "
                    "FROM etf_holding_stats ORDER BY snapshot_date DESC"
                )
            ).fetchall()
        except Exception:  # noqa: BLE001 — view not present yet (tests)
            raw = []
            view_missing = True
    else:
        raw = []
        view_missing = True

    if view_missing:
        # Fallback aggregation (SQLite tests / pre-migration safety).
        agg_rows = (
            db.query(
                ETFHolding.snapshot_date.label("snapshot_date"),
                func.count(distinct(ETFHolding.etf_code)).label("etf_count"),
                func.count().label("row_count"),
                func.count(distinct(ETFHolding.source)).label("source_count"),
                func.group_concat(ETFHolding.source.distinct()).label("sources"),
                func.min(ETFHolding.created_at).label("first_ingested_at"),
                func.max(ETFHolding.created_at).label("last_ingested_at"),
            )
            .filter(ETFHolding.snapshot_date.isnot(None))
            .group_by(ETFHolding.snapshot_date)
            .order_by(ETFHolding.snapshot_date.desc())
            .all()
        )
        for r in agg_rows:
            snap = r.snapshot_date
            if isinstance(snap, datetime):
                snap = snap.date()
            days_ago = (today - snap).days if snap else 0
            etf_count = int(r.etf_count or 0)
            coverage = (
                (etf_count / eligible * 100.0) if eligible > 0 else 0.0
            )
            sources = [
                s for s in (r.sources or "").split(",") if s
] if r.sources else []
            rows.append(
                SnapshotCoverage(
                    snapshot_date=snap,
                    etf_count=etf_count,
                    row_count=int(r.row_count or 0),
                    source_count=int(r.source_count or 0),
                    sources=sources,
                    days_ago=days_ago,
                    eligible_etf_count=eligible,
                    coverage_pct=coverage,
                    coverage_alerts=_compute_alerts(days_ago, coverage),
                )
            )
        return rows

    for r in raw:
        snap = r.snapshot_date
        if isinstance(snap, datetime):
            snap = snap.date()
        etf_count = int(r.etf_count or 0)
        days_ago = int(r.days_ago or 0)
        coverage = (etf_count / eligible * 100.0) if eligible > 0 else 0.0
        sources = list(r.sources or [])
        rows.append(
            SnapshotCoverage(
                snapshot_date=snap,
                etf_count=etf_count,
                row_count=int(r.row_count or 0),
                source_count=int(r.source_count or 0),
                sources=sources,
                days_ago=days_ago,
                eligible_etf_count=eligible,
                coverage_pct=coverage,
                coverage_alerts=_compute_alerts(days_ago, coverage),
            )
        )
    return rows


def get_coverage_for(db: Session, snapshot_date: date) -> SnapshotCoverage | None:
    """Return the coverage row for ``snapshot_date`` (or None if no data)."""
    for row in list_snapshot_stats(db):
        if row.snapshot_date == snapshot_date:
            return row
    return None


def get_latest_coverage(db: Session) -> SnapshotCoverage | None:
    """Return the most recent snapshot's coverage (or None if no data)."""
    rows = list_snapshot_stats(db)
    return rows[0] if rows else None


def list_unavailable(db: Session) -> list[dict[str, Any]]:
    """Return the full blacklist, ordered by category then code."""
    stmt = (
        select(ETFHoldingUnavailable)
        .order_by(
            ETFHoldingUnavailable.category,
            ETFHoldingUnavailable.etf_code,
        )
    )
    items: list[dict[str, Any]] = []
    for row in db.execute(stmt).scalars().all():
        items.append(
            {
                "etf_code": row.etf_code,
                "category": row.category,
                "reason": row.reason,
                "marked_at": row.marked_at.isoformat()
                if row.marked_at
                else None,
                "marked_by": row.marked_by,
            }
        )
    return items
