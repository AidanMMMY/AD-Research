"""Email verification codes for self-service registration (2026-10-25).

Only the SHA-256 hash of the 6-digit code is stored — the plaintext code
exists solely inside the outgoing email. ``attempts`` counts failed
verifications; reaching the cap (5) voids the row. ``consumed_at`` is set
on successful use or when superseded by a resend.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, func

from app.core.database import Base


class EmailVerification(Base):
    """One verification code issued for a user's email."""

    __tablename__ = "email_verifications"
    __table_args__ = (Index("ix_email_verifications_user_id", "user_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Row ID")
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Owner user",
    )
    code_hash = Column(String(64), nullable=False, comment="SHA-256 of the 6-digit code")
    expires_at = Column(DateTime(timezone=True), nullable=False, comment="Code TTL (10 min)")
    attempts = Column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Failed verification attempts",
    )
    consumed_at = Column(DateTime(timezone=True), nullable=True, comment="Used / superseded at")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Creation time",
    )
