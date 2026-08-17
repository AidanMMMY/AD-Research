"""Notification API routes."""


import asyncio
import json
import logging
from collections.abc import AsyncGenerator

# anyio 随 FastAPI/Starlette 传递安装，to_thread.run_sync 与 FastAPI
# 内部共用同一线程池。
import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user, get_notification_service
from app.core.database import SessionLocal
from app.core.log_sanitize import sanitize
from app.schemas.notification import (
    NotificationConfigCreate,
    NotificationConfigResponse,
    NotificationConfigUpdate,
    NotificationLogListResponse,
    SendTestResponse,
)
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])

# SSE tuning: emit a keepalive comment on every tick, and re-poll the
# notification log for the caller so freshly-sent alerts surface live.
_SSE_INTERVAL_SECONDS = 5
_SSE_MAX_LIFETIME_SECONDS = 300
# Query-string keys that would smuggle a JWT past the header-only contract.
_JWT_QUERY_KEYS = ("token", "access_token", "jwt", "authorization")


@router.get("/configs", response_model=list[NotificationConfigResponse])
def list_configs(
    service: NotificationService = Depends(get_notification_service),
    current_user = Depends(get_current_user),
):
    """List all notification configurations."""
    return service.get_configs(user_id=current_user.id)


@router.post("/configs", response_model=NotificationConfigResponse, status_code=201)
def create_config(
    data: NotificationConfigCreate,
    service: NotificationService = Depends(get_notification_service),
    current_user = Depends(get_current_user),
):
    """Create a new notification configuration."""
    return service.create_config(
        name=data.name,
        channel_type=data.channel_type,
        config_json=data.config_json,
        user_id=current_user.id,
    )


@router.put("/configs/{config_id}", response_model=NotificationConfigResponse)
def update_config(
    config_id: int,
    data: NotificationConfigUpdate,
    service: NotificationService = Depends(get_notification_service),
    current_user = Depends(get_current_user),
):
    """Update a notification configuration."""
    update_data = data.model_dump(exclude_unset=True)
    result = service.update_config(config_id, user_id=current_user.id, **update_data)
    if not result:
        raise HTTPException(status_code=404, detail="Config not found")
    return result


@router.delete("/configs/{config_id}", status_code=204)
def delete_config(
    config_id: int,
    service: NotificationService = Depends(get_notification_service),
    current_user = Depends(get_current_user),
):
    """Delete a notification configuration."""
    if not service.delete_config(config_id, user_id=current_user.id):
        raise HTTPException(status_code=404, detail="Config not found")
    return None


@router.post("/configs/{config_id}/test", response_model=SendTestResponse)
def test_config(
    config_id: int,
    service: NotificationService = Depends(get_notification_service),
    current_user = Depends(get_current_user),
):
    """Test a notification configuration."""
    result = service.send_notification(config_id, test=True, user_id=current_user.id)
    return SendTestResponse(**result)


@router.get("/logs", response_model=NotificationLogListResponse)
def get_logs(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=200, description="Items per page"),
    service: NotificationService = Depends(get_notification_service),
    current_user = Depends(get_current_user),
):
    """Get notification send logs (paginated).

    Each item contains: id, user_id (config name), channel, target,
    report_id, status, error, sent_at, created_at.
    """
    return service.get_logs(page=page, page_size=page_size, user_id=current_user.id)


def _poll_recent_logs(user_id: int) -> dict:
    """SSE 轮询用的同步查询：每次调用新建并关闭独立 Session。

    由 async 生成器经 ``anyio.to_thread.run_sync`` 丢到线程池执行——
    同步 SQLAlchemy 查询直接在 async 生成器里跑会阻塞 uvicorn 事件
    循环（2026-08-17 审计 HIGH）。session 不跨线程共享，也不复用
    请求作用域的 session（后者会在整条 SSE 存活期内占用池连接）。
    """
    db = SessionLocal()
    try:
        return NotificationService(db).get_logs(page=1, page_size=5, user_id=user_id)
    finally:
        db.close()


async def _notification_event_stream(user_id: int) -> AsyncGenerator[str, None]:
    """Yield SSE events describing the caller's most recent notification logs.

    Emits an initial ``connected`` event, then re-polls the log every
    ``_SSE_INTERVAL_SECONDS`` and pushes a snapshot whenever the newest log
    id advances. A keepalive comment is always sent so proxies don't close
    an idle connection.
    """
    yield f"event: connected\ndata: {json.dumps({'ok': True})}\n\n"

    last_seen_id: int | None = None
    loop = asyncio.get_event_loop()
    deadline = loop.time() + _SSE_MAX_LIFETIME_SECONDS

    while loop.time() < deadline:
        try:
            page = await anyio.to_thread.run_sync(_poll_recent_logs, user_id)
            items = page.get("items", [])
            newest_id = items[0]["id"] if items else None
            if newest_id != last_seen_id:
                last_seen_id = newest_id
                yield f"data: {json.dumps({'items': items}, ensure_ascii=False)}\n\n"
            else:
                yield ": keepalive\n\n"
        except Exception as exc:  # noqa: BLE001 — stream must not 500 mid-flight
            logger.error("Notification SSE poll failed: %s", sanitize(str(exc)))
            yield f"event: error\ndata: {json.dumps({'error': 'poll_failed'})}\n\n"
        await asyncio.sleep(_SSE_INTERVAL_SECONDS)


@router.get("/stream")
async def notification_stream(
    request: Request,
    current_user=Depends(get_current_user),
):
    """SSE stream of the caller's notification activity (ops P1-2).

    **Header-only auth.** The JWT MUST arrive via ``Authorization: Bearer``
    (already enforced by the router-level ``get_current_user`` dependency).
    Passing the token through the query string — the classic EventSource
    work-around and a common way for a bookmarked/leaked URL to be scraped —
    is rejected with a WARNING log entry rather than silently honoured.
    """
    smuggled = [k for k in _JWT_QUERY_KEYS if k in request.query_params]
    if smuggled:
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "")
        logger.warning(
            "Rejected notification SSE with JWT in query string "
            "(keys=%s ip=%s ua=%s)",
            smuggled,
            sanitize(client_ip),
            sanitize(user_agent),
        )
        raise HTTPException(
            status_code=401,
            detail=(
                "Authenticate the SSE stream via the Authorization header, "
                "not the query string."
            ),
        )

    return StreamingResponse(
        _notification_event_stream(current_user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
