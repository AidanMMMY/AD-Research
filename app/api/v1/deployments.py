"""Deployment dashboard admin API routes.

Provides Vercel-style deployment history, server health, and log streaming
accessible only by admin users.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt

from app.config import auth_settings
from app.api.deps import require_admin
from app.schemas.auth import UserResponse
from app.schemas.deployment import ContainerStats, DeploymentRun, LogLine, ServerHealth
from app.services.deployment_service import (
    get_container_logs,
    get_run_logs,
    get_server_health,
    list_workflow_runs,
    start_log_tailer,
    stop_log_tailer,
    trigger_workflow_dispatch,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# SSE auth helper — EventSource cannot send custom headers, so we accept
# a ``token`` query parameter as a fallback for the SSE endpoint only.
# ---------------------------------------------------------------------------


async def _require_admin_for_sse(request: Request) -> UserResponse:
    """Admin auth that checks Bearer header first, falls back to ``?token=``.

    EventSource in browsers cannot set custom HTTP headers, so the SSE
    streaming endpoint also accepts a query-parameter JWT.
    """
    # 1. Try Bearer header (works for curl / swagger)
    auth_header = request.headers.get("Authorization", "")
    token: str | None = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]

    # 2. Fallback to query parameter (for EventSource)
    if not token:
        token = request.query_params.get("token", "")

    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        payload = jwt.decode(token, auth_settings.SECRET_KEY, algorithms=["HS256"])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError as err:
        raise HTTPException(status_code=401, detail="Invalid token") from err

    # Verify user exists and is admin
    from app.core.database import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid or inactive user")
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        return UserResponse(id=user.id, username=user.username, role=user.role)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Deployment history
# ---------------------------------------------------------------------------


@router.get("/deployments", response_model=list[DeploymentRun])
def api_list_deployments(
    _admin: UserResponse = Depends(require_admin),
):
    """List recent GitHub Actions deployment runs (admin only)."""
    runs = list_workflow_runs(per_page=20)
    return runs


@router.get("/deployments/{run_id}/logs")
def api_get_deployment_logs(
    run_id: int,
    _admin: UserResponse = Depends(require_admin),
):
    """Get logs for a specific workflow run (admin only)."""
    logs = get_run_logs(run_id)
    return {"run_id": run_id, "logs": logs}


@router.post("/deployments/trigger")
def api_trigger_deploy(
    _admin: UserResponse = Depends(require_admin),
):
    """Manually trigger a redeploy via GitHub Actions workflow_dispatch (admin only)."""
    result = trigger_workflow_dispatch()
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("error", "Unknown error"))
    return {"message": "Deployment triggered successfully"}


# ---------------------------------------------------------------------------
# Server health
# ---------------------------------------------------------------------------


@router.get("/server/health", response_model=ServerHealth)
def api_server_health(
    _admin: UserResponse = Depends(require_admin),
):
    """Get container health and resource usage (admin only)."""
    return get_server_health()


# ---------------------------------------------------------------------------
# Container logs (snapshot)
# ---------------------------------------------------------------------------


@router.get("/containers/{container}/logs")
def api_container_logs(
    container: str,
    tail: int = Query(200, ge=1, le=1000),
    _admin: UserResponse = Depends(require_admin),
):
    """Get recent log lines for a container (admin only)."""
    lines = get_container_logs(container, tail=tail)
    return {"container": container, "lines": lines}


# ---------------------------------------------------------------------------
# Log streaming via SSE
# ---------------------------------------------------------------------------


@router.get("/logs/stream")
async def api_stream_logs(
    container: str = Query("adresearch-backend"),
    _admin: UserResponse = Depends(_require_admin_for_sse),
):
    """Stream container logs in real-time via Server-Sent Events (admin only).

    Connects to Redis pub/sub for live log lines from the background
    ``docker logs -f`` tailer.  The tailer is started on first connection
    and stopped when no subscribers remain.
    """
    from app.core.redis_client import get_redis_client

    redis_client = get_redis_client()
    channel = f"deploy:logs:{container}"

    # Ensure tailer is running
    start_log_tailer(container)

    async def event_generator():
        pubsub = redis_client.pubsub()
        try:
            pubsub.subscribe(channel)
            # Send initial connected event
            yield f"event: connected\ndata: {json.dumps({'container': container})}\n\n"

            while True:
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("type") == "message":
                    data = message.get("data")
                    if data:
                        yield f"event: log\ndata: {data}\n\n"
                else:
                    # Keep-alive comment to prevent proxy timeouts
                    yield ": keepalive\n\n"

                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("SSE stream error for %s", container)
        finally:
            try:
                pubsub.unsubscribe(channel)
            except Exception:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/logs/stream/{container}/start")
def api_start_log_stream(
    container: str,
    _admin: UserResponse = Depends(require_admin),
):
    """Start the background log tailer for a container (admin only)."""
    start_log_tailer(container)
    return {"message": f"Log tailer started for {container}"}


@router.post("/logs/stream/{container}/stop")
def api_stop_log_stream(
    container: str,
    _admin: UserResponse = Depends(require_admin),
):
    """Stop the background log tailer for a container (admin only)."""
    stop_log_tailer(container)
    return {"message": f"Log tailer stopped for {container}"}
