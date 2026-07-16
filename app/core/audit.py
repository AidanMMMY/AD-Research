"""Audit-log helpers for admin write operations.

Functions in this module wrap a SQLAlchemy session around an
``AuditLog`` insert so that any admin endpoint (POST/PUT/PATCH/DELETE)
can call ``record_audit(...)`` after a successful mutation.

Design notes:
  * **Fail-open on infra errors**: if the DB is down, the user's write
    should still succeed (and the audit miss surfaces in monitoring).
    We swallow all DB exceptions and log them at WARNING.
  * **Single-row helper**: ``record_audit(...)`` inserts exactly one
    ``AuditLog`` row. There is no buffering / batch flush — admin
    traffic is low frequency so the round-trip cost is negligible.
  * **IP resolution**: prefer the first hop of ``X-Forwarded-For`` if
    present (we sit behind Nginx), else fall back to ``request.client.host``.
  * **Diff payload**: callers pass a dict of the body keys actually
    changed. We never log raw password fields — the helper accepts an
    optional ``redact_keys`` set (default: ``{"password", "new_password",
    "password_hash"}``).

The function signature intentionally uses primitive types (no FastAPI
``Request`` import) so it stays usable from background jobs and tests.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

# Keys whose values must NEVER be persisted in ``payload_diff`` even
# if the caller forgets to scrub them.
_DEFAULT_REDACT_KEYS = frozenset(
    {"password", "new_password", "old_password", "password_hash", "token", "refresh_token"}
)


def _scrub(value: Any, redact_keys: Iterable[str]) -> Any:
    """Replace sensitive values with ``"***"`` inside nested dicts/lists."""
    redact = {k for k in redact_keys}
    if isinstance(value, dict):
        return {
            k: ("***" if k in redact else _scrub(v, redact)) for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub(v, redact) for v in value]
    return value


def record_audit(
    db: Session,
    *,
    action: str,
    actor_user_id: int | None = None,
    actor_username: str | None = None,
    target_type: str | None = None,
    target_id: str | int | None = None,
    payload: dict[str, Any] | None = None,
    ip: str | None = None,
    status_code: int | None = None,
    detail: str | None = None,
    redact_keys: Iterable[str] = _DEFAULT_REDACT_KEYS,
) -> None:
    """Insert one ``audit_log`` row, swallowing DB errors.

    ``action`` is the canonical method+route slug, e.g.
    ``"POST /admin/users"`` or ``"DELETE /admin/users/42"``.
    """
    payload_diff = None
    if payload is not None:
        try:
            payload_diff = _scrub(payload, redact_keys)
            # Serialise to JSON-friendly form so it survives the JSONB cast
            # in case callers passed tuples / sets.
            json.dumps(payload_diff, default=str)
        except (TypeError, ValueError) as exc:
            logger.warning("audit_log payload not JSON-serialisable: %s", exc)
            payload_diff = None

    target_id_str = str(target_id) if target_id is not None else None

    try:
        row = AuditLog(
            actor_user_id=actor_user_id,
            actor_username=actor_username,
            action=action,
            target_type=target_type,
            target_id=target_id_str,
            payload_diff=payload_diff,
            ip=(ip[:64] if ip else None),
            status_code=status_code,
            detail=(detail[:500] if detail else None),
        )
        db.add(row)
        db.commit()
    except Exception as exc:  # pragma: no cover — observability must not break ops
        logger.warning("audit_log insert failed for action=%s: %s", action, exc)
        try:
            db.rollback()
        except Exception:
            pass


def client_ip_from_headers(headers: dict[str, str] | None) -> str | None:
    """Return the best-guess client IP from an HTTP header dict.

    Honours ``X-Forwarded-For`` (first hop) then ``X-Real-IP``.
    """
    if not headers:
        return None
    xff = headers.get("x-forwarded-for") or headers.get("X-Forwarded-For")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    real = headers.get("x-real-ip") or headers.get("X-Real-IP")
    return real.strip() if real else None