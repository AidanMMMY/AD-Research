"""Admin: 数据 API 通道使用情况（2026-11-04）。

聚合 ``data_api_access_log``（X-API-Key 外部只读数据消费方通道的审计
表）供管理后台展示。admin-only；不在对外交接文档中出现。
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models.data_api_access_log import DataApiAccessLog
from app.schemas.auth import UserResponse

router = APIRouter()


@router.get("/data-api/usage")
def get_data_api_usage(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    _admin: UserResponse = Depends(require_admin),
) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    base = db.query(DataApiAccessLog).filter(DataApiAccessLog.created_at >= since)

    total = base.count()
    if total == 0:
        return {
            "days": days,
            "totals": {"requests": 0, "errors": 0, "avg_ms": None},
            "by_day": [],
            "top_paths": [],
            "by_user": [],
            "recent": [],
        }

    avg_ms = base.with_entities(func.avg(DataApiAccessLog.duration_ms)).scalar()
    errors = base.filter(DataApiAccessLog.status_code >= 400).count()

    day_expr = func.date(DataApiAccessLog.created_at).label("day")
    by_day = (
        db.query(
            day_expr,
            func.count(DataApiAccessLog.id),
            func.avg(DataApiAccessLog.duration_ms),
            func.sum(case((DataApiAccessLog.status_code >= 400, 1), else_=0)),
        )
        .filter(DataApiAccessLog.created_at >= since)
        .group_by(day_expr)
        .order_by(day_expr)
        .all()
    )

    top_paths = (
        db.query(
            DataApiAccessLog.path,
            func.count(DataApiAccessLog.id),
            func.avg(DataApiAccessLog.duration_ms),
        )
        .filter(DataApiAccessLog.created_at >= since)
        .group_by(DataApiAccessLog.path)
        .order_by(func.count(DataApiAccessLog.id).desc())
        .limit(15)
        .all()
    )

    by_user = (
        db.query(
            DataApiAccessLog.username,
            func.count(DataApiAccessLog.id),
        )
        .filter(DataApiAccessLog.created_at >= since)
        .group_by(DataApiAccessLog.username)
        .all()
    )

    recent_rows = base.order_by(DataApiAccessLog.created_at.desc()).limit(100).all()

    return {
        "days": days,
        "totals": {
            "requests": total,
            "errors": errors,
            "avg_ms": round(float(avg_ms), 1) if avg_ms is not None else None,
        },
        "by_day": [
            {
                "date": str(d),
                "requests": int(c),
                "avg_ms": round(float(a), 1) if a is not None else None,
                "errors": int(e or 0),
            }
            for d, c, a, e in by_day
        ],
        "top_paths": [
            {"path": p, "requests": int(c), "avg_ms": round(float(a), 1) if a is not None else None}
            for p, c, a in top_paths
        ],
        "by_user": [{"username": u, "requests": int(c)} for u, c in by_user],
        "recent": [
            {
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "username": r.username,
                "method": r.method,
                "path": r.path,
                "status_code": r.status_code,
                "duration_ms": r.duration_ms,
                "client_ip": r.client_ip,
                "user_agent": r.user_agent,
            }
            for r in recent_rows
        ],
    }
