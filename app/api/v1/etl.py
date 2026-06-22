"""ETL API routes.

Provides endpoints for querying ETL job execution status and logs.
"""


from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.etl import ETLLog

router = APIRouter()


@router.get("/status")
def get_etl_status(
    job_name: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get ETL job execution logs.

    Optionally filter by job_name and/or status.
    """
    query = db.query(ETLLog)

    if job_name:
        query = query.filter(ETLLog.job_name == job_name)
    if status:
        query = query.filter(ETLLog.status == status)

    logs = query.order_by(ETLLog.created_at.desc()).limit(limit).all()

    return {
        "items": [
            {
                "id": log.id,
                "job_name": log.job_name,
                "source": log.source,
                "status": log.status,
                "start_time": log.start_time.isoformat() if log.start_time else None,
                "end_time": log.end_time.isoformat() if log.end_time else None,
                "records_count": log.records_count,
                "error_msg": log.error_msg,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
        "count": len(logs),
    }
