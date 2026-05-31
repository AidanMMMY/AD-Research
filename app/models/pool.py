"""ETF pool-related ORM models.

Contains tables for ETF pools and pool members with soft-delete design.
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from app.core.database import Base


class ETFPools(Base):
    """ETF pool definition table."""

    __tablename__ = "etf_pools"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    name = Column(String(100), nullable=False, comment="Pool name")
    description = Column(Text, comment="Pool description")
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


class PoolMember(Base):
    """ETF pool member table with soft-delete design.

    A member is considered "active" when removed_at is NULL.
    Setting removed_at to a timestamp marks the member as removed.
    """

    __tablename__ = "pool_member"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    pool_id = Column(
        Integer,
        ForeignKey("etf_pools.id", ondelete="CASCADE"),
        nullable=False,
        comment="Pool ID",
    )
    etf_code = Column(
        String(20),
        ForeignKey("etf_info.code", ondelete="CASCADE"),
        nullable=False,
        comment="ETF code",
    )
    added_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Added time",
    )
    removed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Removed time (NULL = currently in pool)",
    )
    notes = Column(Text, comment="Notes")

    __table_args__ = (
        UniqueConstraint(
            "pool_id", "etf_code", "removed_at", name="uq_pool_member_pool_etf_removed"
        ),
        Index(
            "idx_pool_members_pool",
            "pool_id",
            postgresql_where=(removed_at.is_(None)),
        ),
        Index(
            "idx_pool_members_etf",
            "etf_code",
            postgresql_where=(removed_at.is_(None)),
        ),
    )
