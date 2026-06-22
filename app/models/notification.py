"""Notification configuration and log models."""

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, func

from app.core.database import Base


class NotificationConfig(Base):
    """Notification channel configuration."""

    __tablename__ = "notification_config"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    name = Column(String(100), nullable=False, comment="Config name")
    channel_type = Column(
        String(20),
        nullable=False,
        comment="Channel type: webhook/email",
    )
    config_json = Column(JSON, nullable=False, comment="Channel-specific config")
    is_active = Column(Boolean, default=True, comment="Is active")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Creation time",
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )


class NotificationLog(Base):
    """Notification send log."""

    __tablename__ = "notification_log"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    config_id = Column(
        Integer,
        ForeignKey("notification_config.id", ondelete="CASCADE"),
        nullable=False,
        comment="Config ID",
    )
    report_id = Column(
        Integer,
        ForeignKey("report_metadata.id", ondelete="SET NULL"),
        comment="Report ID",
    )
    status = Column(
        String(20),
        default="pending",
        comment="Status: pending/success/failed",
    )
    error_msg = Column(String(500), comment="Error message")
    sent_at = Column(DateTime(timezone=True), comment="Send time")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Creation time",
    )
