"""Internal API endpoints for trusted non-user callers.

These endpoints exist for *machine-to-machine* integrations — primarily the
``agent/scripts/orchestrate_v2.py`` watchdog on ECS. They are NOT exposed in
the user-facing OpenAPI by default; authentication uses a shared bearer
token (``INTERNAL_API_TOKEN``) that the cron scripts read from the
filesystem. Without the token the route returns 403 — same posture as an
API-key webhook.

The first caller we support is the orchestrate watchdog: it POSTs an
aggregate failure summary and we drop a NotificationLog row so the existing
``/admin/etl-status`` / ``/api/v1/notifications`` consumers surface the
alerts. This fills the "8-source silent failure for 16h" gap noted in
``docs/dev-notes/20260720-ecs-ops-audit-and-fixes.md`` — until this commit,
a worker timeout or docker image loss simply meant no cron output and no
human notification.

Endpoints
---------
* ``POST /api/v1/internal/orchestrate-alert`` — record an orchestrate
  failure summary as a NotificationLog row (no config_id needed; we pick
  an internal channel type).
"""
from __future__ import annotations

import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# --------------------------------------------------------------------------- #
# Auth                                                                        #
# --------------------------------------------------------------------------- #


def _expected_token() -> str | None:
    """Return the expected internal token, or ``None`` if not configured.

    The token is read from ``INTERNAL_API_TOKEN`` at module import. If the
    variable is missing or empty, *every* call returns 403 — we never fall
    back to an unauthenticated mode. This lets ops generate a random
    token once (``openssl rand -hex 32``) and rotate it without code
    changes.
    """
    token = os.getenv("INTERNAL_API_TOKEN", "").strip()
    return token or None


def require_internal_token(request: Request) -> None:
    """FastAPI dependency that enforces the internal bearer token."""
    expected = _expected_token()
    if not expected:
        raise HTTPException(status_code=503, detail="INTERNAL_API_TOKEN not configured")
    header = request.headers.get("authorization", "")
    bearer = header[7:].strip() if header.lower().startswith("bearer ") else ""
    # Constant-time comparison so we don't leak token info via timing.
    if not bearer or not _secure_compare(bearer, expected):
        raise HTTPException(status_code=403, detail="invalid internal token")


def _secure_compare(a: str, b: str) -> bool:
    """Constant-time string comparison.

    We use :func:`hmac.compare_digest` because Python 3.11's ``hashlib``
    module does not expose ``compare_digest`` directly on some Homebrew
    builds; ``hmac`` is a stable wrapper around the same primitive.
    """
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# --------------------------------------------------------------------------- #
# Schemas                                                                     #
# --------------------------------------------------------------------------- #


class OrchestrateAlertItem(BaseModel):
    """One worker result inside an orchestrate aggregate."""

    name: str = Field(..., description="worker name, e.g. 'xueqiu_playwright'")
    exit_code: int = Field(..., description="process exit code; -1 == timeout, -2 == orchestrator crash")
    items: int = Field(default=0, description="records the worker reported fetching")
    duration: float = Field(default=0.0, description="seconds the worker took")
    error: str | None = Field(default=None, description="short error reason")


class OrchestrateAlertRequest(BaseModel):
    """Aggregate summary POSTed by ``agent/scripts/orchestrate_v2.py``."""

    failed_workers: list[OrchestrateAlertItem] = Field(
        default_factory=list,
        description="workers whose exit was non-zero or that threw; empty list == no failures",
    )
    schedule: str = Field(default="all", description="which schedule ran: all/quick/logged_in")
    total_duration_seconds: float = Field(default=0.0)
    host: str | None = Field(default=None, description="hostname of the cron runner")
    threshold: int = Field(default=2, description="threshold passed to the watchdog; recorded for audit")


class OrchestrateAlertResponse(BaseModel):
    accepted: bool
    notification_log_id: int | None = None
    status: str  # one of: "skipped" | "below_threshold" | "logged"
    failed_count: int


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _format_summary(payload: OrchestrateAlertRequest) -> str:
    """Render an alert payload as a single multi-line string for the log."""
    lines = [
        "ORCHESTRATE_WATCHDOG",
        f"schedule={payload.schedule} total={payload.total_duration_seconds}s host={payload.host or '-'}"
        f" failed={len(payload.failed_workers)}/{payload.threshold}",
    ]
    for w in payload.failed_workers[:10]:
        err = (w.error or "").replace("\n", " ").strip()
        if len(err) > 120:
            err = err[:120] + "..."
        lines.append(
            f" - {w.name} exit={w.exit_code} items={w.items} duration={w.duration}s err={err}"
        )
    return "\n".join(lines)


def _ensure_alert_config(db: Session) -> int:
    """Return the singleton NotificationConfig id used for system alerts.

    We don't expose this in the UI; it's just a sink row so the existing
    ``notification_log`` consumer can join. Any user_id=1 row works as a
    placeholder; we look up by channel_type + name to avoid hard-coding ids.
    """
    from app.models.notification import NotificationConfig

    cfg = (
        db.query(NotificationConfig)
        .filter(NotificationConfig.channel_type == "system_alert")
        .filter(NotificationConfig.name == "orchestrate_watchdog")
        .one_or_none()
    )
    if cfg is not None:
        return cfg.id

    cfg = NotificationConfig(
        user_id=1,
        name="orchestrate_watchdog",
        channel_type="system_alert",
        config_json={"sink": True, "auto_created": True},
        is_active=True,
    )
    db.add(cfg)
    db.flush()  # populate cfg.id without committing yet
    return cfg.id


# --------------------------------------------------------------------------- #
# Route                                                                       #
# --------------------------------------------------------------------------- #


@router.post(
    "/orchestrate-alert",
    response_model=OrchestrateAlertResponse,
    dependencies=[Depends(require_internal_token)],
)
def record_orchestrate_alert(
    payload: OrchestrateAlertRequest,
    db: Session = Depends(get_db),
) -> OrchestrateAlertResponse:
    """Receive an orchestrate failure aggregate and (when warranted) record it.

    Behavior:
      * ``failed_workers`` empty → ``skipped`` (no failures to surface).
      * failed count < threshold → ``below_threshold`` (likely one-shot
        flake; not worth alerting).
      * otherwise → ``logged`` and a ``NotificationLog`` row is committed
        so downstream consumers (``/admin/etl-status``,
        ``/api/v1/notifications/logs``) see it immediately.
    """
    from app.models.notification import NotificationLog

    failed_count = len(payload.failed_workers)

    if failed_count == 0:
        logger.info("orchestrate watchdog: no failed workers (schedule=%s)", payload.schedule)
        return OrchestrateAlertResponse(
            accepted=True,
            notification_log_id=None,
            status="skipped",
            failed_count=0,
        )

    if failed_count < payload.threshold:
        logger.info(
            "orchestrate watchdog: failed=%d below threshold=%d — not logging",
            failed_count, payload.threshold,
        )
        return OrchestrateAlertResponse(
            accepted=True,
            notification_log_id=None,
            status="below_threshold",
            failed_count=failed_count,
        )

    config_id = _ensure_alert_config(db)
    summary = _format_summary(payload)

    log_row = NotificationLog(
        config_id=config_id,
        status="failed" if failed_count >= max(payload.threshold, 3) else "success",
        error_msg=summary[:500],  # column size cap (String(500))
        sent_at=datetime.now(timezone.utc),
    )
    db.add(log_row)
    db.commit()
    db.refresh(log_row)

    logger.warning(
        "orchestrate watchdog ALERT  failed=%d/%d  schedule=%s  log_id=%s",
        failed_count, payload.threshold, payload.schedule, log_row.id,
    )
    return OrchestrateAlertResponse(
        accepted=True,
        notification_log_id=log_row.id,
        status="logged",
        failed_count=failed_count,
    )


@router.get(
    "/health",
    summary="Liveness probe for the internal API (token required).",
    dependencies=[Depends(require_internal_token)],
)
def internal_health() -> dict[str, Any]:
    """Cheap endpoint used by the agent watchdog to verify backend reachability."""
    return {"status": "ok", "scope": "internal"}
