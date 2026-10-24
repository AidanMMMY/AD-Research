"""User account model."""

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, false, func

from app.core.database import Base


class User(Base):
    """Platform user account."""

    __tablename__ = "users"
    # Unique *index* (not inline unique=True) so the constraint name stays
    # aligned with the Alembic migration; multiple NULL emails are allowed
    # in both PostgreSQL and SQLite.
    __table_args__ = (Index("uq_users_email", "email", unique=True),)

    id = Column(Integer, primary_key=True, autoincrement=True, comment="User ID")
    username = Column(String(50), nullable=False, unique=True, comment="Login username")
    password_hash = Column(String(255), nullable=False, comment="Bcrypt password hash")
    role = Column(String(20), nullable=False, default="user", comment="User role")
    is_active = Column(Boolean, default=True, nullable=False, comment="Is active")
    # True ⇒ the user must set a new password on next login (set when an
    # admin creates the account or resets its password; cleared by
    # POST /auth/change-password). server_default keeps existing rows False.
    must_change_password = Column(
        Boolean,
        nullable=False,
        server_default=false(),
        comment="Must change password on next login",
    )
    # Self-registration (2026-10-25): email identity + verification gate.
    # NULL for legacy/admin-created accounts — the login gate only applies
    # when registration is enabled AND the row has an email whose
    # verified_at is still NULL.
    email = Column(
        String(255),
        nullable=True,
        comment="Account email (self-registration identity)",
    )
    email_verified_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the account email was verified",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Creation time",
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last update time",
    )
