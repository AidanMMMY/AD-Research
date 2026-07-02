"""A-share micro-structure data read service.

Read-only facade over the four micro-structure tables (龙虎榜 / 沪深港通
/ 融资融券 / 限售解禁).  The ETL side lives in
``app/data/pipelines/microstructure.py``; this module exposes a
narrower API used by the FastAPI router.

The helper functions take an explicit ``Session`` argument rather than
holding one as state, so the FastAPI ``get_db`` dependency can scope
session lifetime correctly.
"""

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.microstructure import (
    HsgtFlow,
    LhbRecord,
    MarginBalance,
    RestrictedRelease,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 龙虎榜 (LHB)
# ---------------------------------------------------------------------------


def list_lhb(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    ts_code: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    sort_dir: str = "desc",
) -> dict[str, Any]:
    """Paginated LHB list with optional ticker + date filters."""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20
    sort_dir_norm = sort_dir.lower() if sort_dir.lower() in ("asc", "desc") else "desc"

    stmt = select(LhbRecord)
    count_stmt = select(func.count(LhbRecord.id))

    if ts_code:
        stmt = stmt.where(LhbRecord.ts_code == ts_code)
        count_stmt = count_stmt.where(LhbRecord.ts_code == ts_code)
    if start_date:
        stmt = stmt.where(LhbRecord.trade_date >= start_date)
        count_stmt = count_stmt.where(LhbRecord.trade_date >= start_date)
    if end_date:
        stmt = stmt.where(LhbRecord.trade_date <= end_date)
        count_stmt = count_stmt.where(LhbRecord.trade_date <= end_date)

    sort_col = LhbRecord.lhb_net_amount if sort_dir_norm == "desc" else LhbRecord.trade_date
    stmt = stmt.order_by(sort_col.desc() if sort_dir_norm == "desc" else sort_col.asc())

    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(
        stmt.offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()

    return {
        "items": [_lhb_to_dict(r) for r in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# 沪深港通 (HSGT)
# ---------------------------------------------------------------------------


def list_hsgt(
    db: Session,
    *,
    days: int = 30,
    flow_type: str | None = None,
) -> dict[str, Any]:
    """Return the last ``days`` of HSGT flows, optionally filtered by type."""
    if days < 1 or days > 365:
        days = 30
    cutoff = date.today() - timedelta(days=days)

    stmt = select(HsgtFlow).where(HsgtFlow.trade_date >= cutoff)
    if flow_type:
        stmt = stmt.where(HsgtFlow.type == flow_type)
    stmt = stmt.order_by(HsgtFlow.trade_date.desc(), HsgtFlow.type.asc())

    rows = db.execute(stmt).scalars().all()
    return {
        "items": [_hsgt_to_dict(r) for r in rows],
        "total": len(rows),
    }


# ---------------------------------------------------------------------------
# 融资融券 (Margin)
# ---------------------------------------------------------------------------


def list_margin(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    ts_code: str | None = None,
    exchange: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    sort_dir: str = "desc",
) -> dict[str, Any]:
    """Paginated margin-balance list with optional filters."""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20
    sort_dir_norm = sort_dir.lower() if sort_dir.lower() in ("asc", "desc") else "desc"

    stmt = select(MarginBalance)
    count_stmt = select(func.count(MarginBalance.id))

    if ts_code:
        stmt = stmt.where(MarginBalance.ts_code == ts_code)
        count_stmt = count_stmt.where(MarginBalance.ts_code == ts_code)
    if exchange:
        stmt = stmt.where(MarginBalance.exchange == exchange.upper())
        count_stmt = count_stmt.where(MarginBalance.exchange == exchange.upper())
    if start_date:
        stmt = stmt.where(MarginBalance.trade_date >= start_date)
        count_stmt = count_stmt.where(MarginBalance.trade_date >= start_date)
    if end_date:
        stmt = stmt.where(MarginBalance.trade_date <= end_date)
        count_stmt = count_stmt.where(MarginBalance.trade_date <= end_date)

    sort_col = (
        MarginBalance.financing_balance
        if sort_dir_norm == "desc"
        else MarginBalance.trade_date
    )
    stmt = stmt.order_by(
        sort_col.desc() if sort_dir_norm == "desc" else sort_col.asc()
    )

    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(
        stmt.offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()

    return {
        "items": [_margin_to_dict(r) for r in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# 限售解禁 (Restricted Release)
# ---------------------------------------------------------------------------


def list_restricted_releases(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    ts_code: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    sort_dir: str = "asc",
) -> dict[str, Any]:
    """Paginated restricted-release list.  Default sort = upcoming soonest first."""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20
    sort_dir_norm = sort_dir.lower() if sort_dir.lower() in ("asc", "desc") else "asc"

    stmt = select(RestrictedRelease)
    count_stmt = select(func.count(RestrictedRelease.id))

    if ts_code:
        stmt = stmt.where(RestrictedRelease.ts_code == ts_code)
        count_stmt = count_stmt.where(RestrictedRelease.ts_code == ts_code)
    if start_date:
        stmt = stmt.where(RestrictedRelease.restricted_date >= start_date)
        count_stmt = count_stmt.where(RestrictedRelease.restricted_date >= start_date)
    if end_date:
        stmt = stmt.where(RestrictedRelease.restricted_date <= end_date)
        count_stmt = count_stmt.where(RestrictedRelease.restricted_date <= end_date)

    stmt = stmt.order_by(
        RestrictedRelease.restricted_date.asc()
        if sort_dir_norm == "asc"
        else RestrictedRelease.restricted_date.desc()
    )

    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(
        stmt.offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()

    return {
        "items": [_release_to_dict(r) for r in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# Summary (dashboard)
# ---------------------------------------------------------------------------


def get_summary(db: Session) -> dict[str, Any]:
    """Return latest-day micro-structure summary for the dashboard.

    Each section is best-effort: a missing section means no fresh data
    was available for that data class on the latest trade date.
    """
    # 1. Latest trade date with any data
    latest_date = (
        db.execute(select(func.max(LhbRecord.trade_date))).scalar()
        or db.execute(select(func.max(HsgtFlow.trade_date))).scalar()
        or db.execute(select(func.max(MarginBalance.trade_date))).scalar()
    )

    summary: dict[str, Any] = {"as_of": latest_date}

    # 2. LHB top 5 net-buy / net-sell stocks for the latest day
    try:
        lhb_day = db.execute(
            select(func.max(LhbRecord.trade_date))
        ).scalar()
        if lhb_day is not None:
            lhb_rows = db.execute(
                select(LhbRecord)
                .where(LhbRecord.trade_date == lhb_day)
                .order_by(LhbRecord.lhb_net_amount.desc())
                .limit(5)
            ).scalars().all()
            top_buyers = [_lhb_to_dict(r) for r in lhb_rows]

            lhb_rows_sell = db.execute(
                select(LhbRecord)
                .where(LhbRecord.trade_date == lhb_day)
                .order_by(LhbRecord.lhb_net_amount.asc())
                .limit(5)
            ).scalars().all()
            top_sellers = [_lhb_to_dict(r) for r in lhb_rows_sell]

            count = db.execute(
                select(func.count(LhbRecord.id)).where(LhbRecord.trade_date == lhb_day)
            ).scalar() or 0

            summary["lhb"] = {
                "trade_date": lhb_day.isoformat() if lhb_day else None,
                "count": int(count),
                "top_buyers": top_buyers,
                "top_sellers": top_sellers,
            }
        else:
            summary["lhb"] = {}
    except Exception as exc:  # noqa: BLE001 - defensive
        logger.warning("get_summary.lhb failed: %s", exc)
        summary["lhb"] = {}

    # 3. HSGT latest-day summary
    try:
        hsgt_day = db.execute(select(func.max(HsgtFlow.trade_date))).scalar()
        if hsgt_day is not None:
            flows = db.execute(
                select(HsgtFlow).where(HsgtFlow.trade_date == hsgt_day)
            ).scalars().all()
            by_type: dict[str, dict[str, Any]] = {}
            for r in flows:
                by_type[r.type] = _hsgt_to_dict(r)
            summary["hsgt"] = {
                "trade_date": hsgt_day.isoformat() if hsgt_day else None,
                "north_net": _net(by_type.get("北向")),
                "sh_net": _net(by_type.get("沪股通")),
                "sz_net": _net(by_type.get("深股通")),
                "rows": list(by_type.values()),
            }
        else:
            summary["hsgt"] = {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_summary.hsgt failed: %s", exc)
        summary["hsgt"] = {}

    # 4. Margin latest-day totals
    try:
        margin_day = db.execute(select(func.max(MarginBalance.trade_date))).scalar()
        if margin_day is not None:
            totals = db.execute(
                select(
                    func.coalesce(func.sum(MarginBalance.financing_balance), 0),
                    func.coalesce(func.sum(MarginBalance.securities_balance), 0),
                ).where(MarginBalance.trade_date == margin_day)
            ).one()
            summary["margin"] = {
                "trade_date": margin_day.isoformat() if margin_day else None,
                "total_financing_balance": float(totals[0] or 0),
                "total_securities_balance": float(totals[1] or 0),
            }
        else:
            summary["margin"] = {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_summary.margin failed: %s", exc)
        summary["margin"] = {}

    # 5. Restricted-release upcoming 30d
    try:
        today = date.today()
        cutoff_30 = today + timedelta(days=30)
        upcoming = db.execute(
            select(func.count(RestrictedRelease.id)).where(
                RestrictedRelease.restricted_date >= today,
                RestrictedRelease.restricted_date <= cutoff_30,
            )
        ).scalar() or 0
        amount_total = db.execute(
            select(func.coalesce(func.sum(RestrictedRelease.restricted_amount), 0)).where(
                RestrictedRelease.restricted_date >= today,
                RestrictedRelease.restricted_date <= cutoff_30,
            )
        ).scalar() or 0
        summary["release"] = {
            "upcoming_30d_count": int(upcoming),
            "upcoming_30d_amount": float(amount_total),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_summary.release failed: %s", exc)
        summary["release"] = {}

    return summary


def get_facets(db: Session) -> dict[str, list[str]]:
    """Return distinct values for filter dropdowns (exchanges, etc.)."""
    exchanges = sorted(
        [
            str(v)
            for v in db.execute(
                select(distinct(MarginBalance.exchange)).where(MarginBalance.exchange.isnot(None))
            ).scalars().all()
            if v
        ]
    )
    return {"exchanges": exchanges}


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------


def _lhb_to_dict(r: LhbRecord) -> dict[str, Any]:
    return {
        "id": r.id,
        "trade_date": r.trade_date.isoformat() if r.trade_date else None,
        "ts_code": r.ts_code,
        "name": r.name,
        "close": float(r.close) if r.close is not None else None,
        "pct_change": float(r.pct_change) if r.pct_change is not None else None,
        "turnover_rate": float(r.turnover_rate) if r.turnover_rate is not None else None,
        "amount": float(r.amount) if r.amount is not None else None,
        "lhb_buy_amount": float(r.lhb_buy_amount) if r.lhb_buy_amount is not None else None,
        "lhb_sell_amount": float(r.lhb_sell_amount) if r.lhb_sell_amount is not None else None,
        "lhb_net_amount": float(r.lhb_net_amount) if r.lhb_net_amount is not None else None,
        "total_buy": float(r.total_buy) if r.total_buy is not None else None,
        "total_sell": float(r.total_sell) if r.total_sell is not None else None,
        "total_net": float(r.total_net) if r.total_net is not None else None,
        "net_buy_amt": float(r.net_buy_amt) if r.net_buy_amt is not None else None,
        "buy_seat_count": r.buy_seat_count,
        "sell_seat_count": r.sell_seat_count,
        "reason": r.reason,
        "source": r.source,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _hsgt_to_dict(r: HsgtFlow) -> dict[str, Any]:
    return {
        "id": r.id,
        "trade_date": r.trade_date.isoformat() if r.trade_date else None,
        "type": r.type,
        "buy_amount": float(r.buy_amount) if r.buy_amount is not None else None,
        "sell_amount": float(r.sell_amount) if r.sell_amount is not None else None,
        "net_amount": float(r.net_amount) if r.net_amount is not None else None,
        "balance": float(r.balance) if r.balance is not None else None,
        "source": r.source,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _margin_to_dict(r: MarginBalance) -> dict[str, Any]:
    return {
        "id": r.id,
        "trade_date": r.trade_date.isoformat() if r.trade_date else None,
        "ts_code": r.ts_code,
        "name": r.name,
        "financing_balance": float(r.financing_balance)
        if r.financing_balance is not None
        else None,
        "financing_buy": float(r.financing_buy) if r.financing_buy is not None else None,
        "securities_balance": float(r.securities_balance)
        if r.securities_balance is not None
        else None,
        "securities_sell": float(r.securities_sell) if r.securities_sell is not None else None,
        "exchange": r.exchange,
        "source": r.source,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _release_to_dict(r: RestrictedRelease) -> dict[str, Any]:
    return {
        "id": r.id,
        "ts_code": r.ts_code,
        "name": r.name,
        "restricted_date": r.restricted_date.isoformat() if r.restricted_date else None,
        "restricted_type": r.restricted_type,
        "restricted_number": float(r.restricted_number)
        if r.restricted_number is not None
        else None,
        "restricted_amount": float(r.restricted_amount)
        if r.restricted_amount is not None
        else None,
        "lift_ratio": float(r.lift_ratio) if r.lift_ratio is not None else None,
        "source": r.source,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _net(row: dict[str, Any] | None) -> float | None:
    if not row:
        return None
    v = row.get("net_amount")
    return float(v) if v is not None else None