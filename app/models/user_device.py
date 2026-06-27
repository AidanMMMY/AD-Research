"""Device management for multi-device login tracking."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func

from app.core.database import Base


class UserDevice(Base):
    """Tracks devices registered for APNs push and multi-device login management."""

    __tablename__ = "user_devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_name = Column(String(100), nullable=False, comment="User-facing name, e.g. 'iPhone 16 Pro'")
    platform = Column(String(20), nullable=False, default="ios", comment="ios / android / web")
    push_token = Column(Text, nullable=True, comment="APNs or FCM device token for push")
    last_active_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
