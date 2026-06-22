"""User account model."""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, func

from app.core.database import Base


class User(Base):
    """Platform user account."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="User ID")
    username = Column(String(50), nullable=False, unique=True, comment="Login username")
    password_hash = Column(String(255), nullable=False, comment="Bcrypt password hash")
    role = Column(String(20), nullable=False, default="user", comment="User role")
    is_active = Column(Boolean, default=True, nullable=False, comment="Is active")
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
