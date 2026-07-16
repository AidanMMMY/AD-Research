"""ETL API routes.

Provides endpoints for querying ETL job execution status and logs, plus
admin-only operations: scheduler job introspection, ad-hoc "run now"
triggers, and one-shot ETL re-runs (ops P1-1 / P1-4).
"""


from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models.etl import ETLLog
from app.schemas.auth import UserResponse
from app.services import scheduler_service

router = APIRouter()


class ETLReRunRequest(BaseModel):
    """Body for POST /etl/re-run."""

    job_name: str = Field(..., description="Scheduler job id to re-run")
    force: bool = Field(False, description="Caller-intent flag (see service docs)")


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


# ── Scheduler ops (admin only) ──────────────────────────────────────────


@router.get("/scheduler/jobs")
def list_scheduler_jobs(
    db: Session = Depends(get_db),
    _: UserResponse = Depends(require_admin),
):
    """List every registered scheduler job with its last-run stats (P1-1)."""
    return {"jobs": scheduler_service.list_jobs(db)}


@router.post("/scheduler/jobs/{job_id}/run-now", status_code=202)
def run_scheduler_job_now(
    job_id: str,
    _: UserResponse = Depends(require_admin),
):
    """Fire a registered scheduler job once, out of band (P1-1)."""
    try:
        result = scheduler_service.run_now(job_id)
    except scheduler_service.JobNotRunnable as err:
        raise HTTPException(
            status_code=400,
            detail=f"Job '{job_id}' is not registered for manual runs",
        ) from err
    return result


@router.post("/re-run", status_code=202)
def rerun_etl_job(
    body: ETLReRunRequest = Body(...),
    _: UserResponse = Depends(require_admin),
):
    """Trigger a one-shot ETL re-run and fire a completion alert (P1-4).

    Responds ``202 Accepted`` with ``{task_id, queued_at}`` — the job runs
    asynchronously in a background thread and notifies admin channels on
    completion via :class:`NotificationService`.
    """
    try:
        result = scheduler_service.trigger_etl_rerun(body.job_name, force=body.force)
    except scheduler_service.JobNotRunnable as err:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown ETL job '{body.job_name}'",
        ) from err
    return {
        "task_id": result["task_id"],
        "queued_at": result.get("queued_at", datetime.now(timezone.utc).isoformat()),
    }

