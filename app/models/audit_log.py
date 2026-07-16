"""Audit log model for admin write operations.

Every admin write (POST / PUT / PATCH / DELETE on admin routers) is
captured here for ops traceability. Captures: actor user_id, action,
target_type, target_id, request body diff, ip, timestamp.

Mirrors the model conventions used in ``app/models/notification.py``.
"""

from sqlalchemy import JSON, Column, DateTime, Integer, String, func

from app.core.database import Base


class AuditLog(Base):
    """Audit log entry for one admin write operation."""

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    actor_user_id = Column(
        Integer,
        nullable=True,
        comment="User who performed the action (null = anonymous / scheduler)",
    )
    actor_username = Column(String(50), nullable=True, comment="Cached username for display")
    action = Column(
        String(40),
        nullable=False,
        comment="HTTP method + endpoint slug, e.g. POST /admin/users",
    )
    target_type = Column(
        String(40),
        nullable=True,
        comment="Resource class, e.g. 'user', 'notification_config'",
    )
    target_id = Column(
        String(80),
        nullable=True,
        comment="Resource id (string for portability, e.g. '42' or 'webhook/3')",
    )
    payload_diff = Column(
        JSON,
        nullable=True,
        comment="Request body (sanitized) — keys changed and their new values",
    )
    ip = Column(
        String(64),
        nullable=True,
        comment="Client IP (X-Forwarded-For first hop if present)",
    )
    status_code = Column(
        Integer,
        nullable=True,
        comment="HTTP response status (when available)",
    )
    detail = Column(
        String(500),
        nullable=True,
        comment="Free-form description or short error message",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When the action was performed",
    )