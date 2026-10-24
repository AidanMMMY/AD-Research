"""Email verification codes for self-service registration (2026-10-25) and
password reset (2026-10-25, same-day follow-up).

Only the SHA-256 hash of the 6-digit code is stored — the plaintext code
exists solely inside the outgoing email. ``attempts`` counts failed
verifications; reaching the cap (5) voids the row. ``consumed_at`` is set
on successful use or when superseded by a resend. ``purpose`` separates the
two issuance flows ('register' | 'password_reset') so a reset code can never
be replayed against /verify-registration and vice versa; rows created before
the column existed keep 'register' semantics via the server default.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, func

from app.core.database import Base

# Issuance purposes (stored in EmailVerification.purpose).
PURPOSE_REGISTER = "register"
PURPOSE_PASSWORD_RESET = "password_reset"


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
    purpose = Column(
        String(20),
        nullable=False,
        default=PURPOSE_REGISTER,
        server_default=PURPOSE_REGISTER,
        comment="Issuance flow: register | password_reset",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Creation time",
    )
