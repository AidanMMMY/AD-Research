"""User favorite/watchlist model."""


from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint, func

from app.core.database import Base


class UserFavorite(Base):
    """User's ETF watchlist / favorites."""

    __tablename__ = "user_favorite"

    id = Column(
        String(50),
        primary_key=True,
        comment="Composite key: username_etf_code",
    )
    username = Column(
        String(50),
        ForeignKey("users.username", ondelete="CASCADE"),
        nullable=False,
        comment="Username from JWT token",
    )
    etf_code = Column(
        String(20),
        ForeignKey("etf_info.code", ondelete="CASCADE"),
        nullable=False,
        comment="ETF code",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="When this favorite was added",
    )

    __table_args__ = (
        UniqueConstraint(
            "username", "etf_code",
            name="uq_user_favorite_username_etf",
        ),
    )
