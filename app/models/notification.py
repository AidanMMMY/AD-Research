"""Notification configuration and log models."""

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func

from app.core.database import Base


class NotificationConfig(Base):
    """Notification channel configuration."""

    __tablename__ = "notification_config"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    user_id = Column(Integer, nullable=False, comment="Owner user ID")
    name = Column(String(100), nullable=False, comment="Config name")
    channel_type = Column(
        String(20),
        nullable=False,
        comment="Channel type: webhook/email",
    )
    config_json = Column(JSON, nullable=False, comment="Channel-specific config")
    # P0-3: webhook URLs are sensitive (they carry the bot's auth token in
    # the URL itself). Store Fernet-encrypted at rest. The encryption key
    # is loaded from NOTIFICATION_ENCRYPTION_KEY env var (or AUTH_SECRET_KEY
    # fallback) — see NotificationService._get_fernet. New rows write here;
    # legacy rows remain readable from config_json["webhook_url"] until the
    # next write triggers a re-encrypt.
    webhook_url_encrypted = Column(
        Text,
        nullable=True,
        comment="Fernet-encrypted webhook URL (P0-3)",
    )
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
