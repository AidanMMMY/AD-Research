"""ETF pool-related ORM models.

Contains tables for ETF pools, pool members, weights, and snapshots
with soft-delete design.
"""

from typing import TYPE_CHECKING

from sqlalchemy import (
    DECIMAL,
    JSON,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.etf import ETFInfo


class ETFPools(Base):
    """ETF pool definition table with soft-delete design."""

    __tablename__ = "etf_pools"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    name = Column(String(100), nullable=False, comment="Pool name")
    description = Column(Text, comment="Pool description")
    deleted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Deletion time (NULL = active)",
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
        comment="Update time",
    )

    members: Mapped[list["PoolMember"]] = relationship(
        "PoolMember",
        back_populates="pool",
        cascade="all, delete-orphan",
        lazy="selectin",
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

    pool: Mapped["ETFPools"] = relationship("ETFPools", back_populates="members")
    etf_info: Mapped["ETFInfo"] = relationship("ETFInfo", lazy="selectin")

    __table_args__ = (
        Index(
            "uq_pool_member_active",
            "pool_id",
            "etf_code",
            unique=True,
            postgresql_where=(removed_at.is_(None)),
        ),
        Index(
            "uq_pool_member_removed",
            "pool_id",
            "etf_code",
            "removed_at",
            unique=True,
            postgresql_where=(removed_at.isnot(None)),
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


class PoolWeight(Base):
    """ETF pool weight allocation table.

    Stores target and suggested weight allocations for each ETF in a pool,
    along with the source of the weight recommendation. Uses soft-delete so
    historical weight data is preserved when a member is removed.
    """

    __tablename__ = "pool_weight"

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
    target_weight = Column(
        DECIMAL(5, 2),
        comment="Target weight percentage (e.g. 25.00 = 25%)",
    )
    suggested_weight = Column(
        DECIMAL(5, 2),
        comment="Suggested weight percentage from algorithm",
    )
    weight_source = Column(
        String(20),
        nullable=False,
        comment="Weight source: manual/equal/score/risk_parity",
    )
    removed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Removed time (NULL = active)",
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
        comment="Update time",
    )

    __table_args__ = (
        Index(
            "uq_pool_weight_active",
            "pool_id",
            "etf_code",
            unique=True,
            postgresql_where=(removed_at.is_(None)),
        ),
    )


class PoolSnapshot(Base):
    """ETF pool snapshot table.

    Stores point-in-time snapshots of pool data (holdings, weights,
    performance metrics) as JSON for historical tracking.
    """

    __tablename__ = "pool_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    pool_id = Column(
        Integer,
        ForeignKey("etf_pools.id", ondelete="CASCADE"),
        nullable=False,
        comment="Pool ID",
    )
    snapshot_date = Column(
        Date,
        nullable=False,
        comment="Snapshot date",
    )
    data = Column(
        JSON,
        nullable=False,
        comment="Snapshot data as JSON",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Creation time",
    )

    __table_args__ = (
        UniqueConstraint(
            "pool_id", "snapshot_date", name="uq_pool_snapshot_pool_date"
        ),
        Index(
            "idx_pool_snapshot_pool_date",
            "pool_id",
            "snapshot_date",
        ),
    )
