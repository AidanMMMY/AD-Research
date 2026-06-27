"""Refresh token model for persistent login sessions."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func

from app.core.database import Base


class RefreshToken(Base):
    """Long-lived refresh token for token rotation.

    Stored in DB so tokens survive server restarts.
    Access tokens are short-lived (15 min) and revoked via Redis blacklist.
    """

    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(255), nullable=False, unique=True, comment="SHA-256 of refresh token")
    device_id = Column(
        String(255),
        nullable=True,
        comment="Optional device identifier for token scoping",
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
