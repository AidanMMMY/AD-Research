"""ETF pool business logic service.

Provides CRUD operations for ETF pools and member management
with soft-delete support.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.etf import ETFInfo
from app.models.pool import ETFPools, PoolMember
from app.schemas.pool import (
    PoolCreate,
    PoolMemberCreate,
    PoolMemberResponse,
    PoolResponse,
    PoolUpdate,
)


class PoolService:
    """Service for ETF pool operations."""

    def __init__(self, db: Session):
        self.db = db

    def list_pools(self) -> List[PoolResponse]:
        """List all pools with their active members."""
        pools = self.db.query(ETFPools).all()
        return [self._to_response(pool) for pool in pools]

    def get_pool(self, pool_id: int) -> Optional[PoolResponse]:
        """Get a single pool by ID."""
        pool = self.db.query(ETFPools).filter(ETFPools.id == pool_id).first()
        return self._to_response(pool) if pool else None

    def create_pool(self, data: PoolCreate) -> PoolResponse:
        """Create a new pool."""
        pool = ETFPools(name=data.name, description=data.description)
        self.db.add(pool)
        self.db.commit()
        self.db.refresh(pool)
        return self._to_response(pool)

    def update_pool(
        self, pool_id: int, data: PoolUpdate
    ) -> Optional[PoolResponse]:
        """Update an existing pool."""
        pool = self.db.query(ETFPools).filter(ETFPools.id == pool_id).first()
        if not pool:
            return None

        if data.name is not None:
            pool.name = data.name
        if data.description is not None:
            pool.description = data.description

        self.db.commit()
        self.db.refresh(pool)
        return self._to_response(pool)

    def delete_pool(self, pool_id: int) -> bool:
        """Delete a pool (hard delete)."""
        pool = self.db.query(ETFPools).filter(ETFPools.id == pool_id).first()
        if not pool:
            return False

        self.db.delete(pool)
        self.db.commit()
        return True

    def add_member(
        self, pool_id: int, data: PoolMemberCreate
    ) -> Optional[PoolResponse]:
        """Add an ETF to a pool."""
        pool = self.db.query(ETFPools).filter(ETFPools.id == pool_id).first()
        if not pool:
            return None

        # Check if the ETF is already an active member
        existing = (
            self.db.query(PoolMember)
            .filter(
                PoolMember.pool_id == pool_id,
                PoolMember.etf_code == data.etf_code,
                PoolMember.removed_at.is_(None),
            )
            .first()
        )
        if existing:
            # Already an active member, just return the pool
            return self._to_response(pool)

        member = PoolMember(
            pool_id=pool_id, etf_code=data.etf_code, notes=data.notes
        )
        self.db.add(member)
        self.db.commit()
        self.db.refresh(pool)
        return self._to_response(pool)

    def remove_member(
        self, pool_id: int, etf_code: str
    ) -> Optional[PoolResponse]:
        """Soft-remove an ETF from a pool."""
        pool = self.db.query(ETFPools).filter(ETFPools.id == pool_id).first()
        if not pool:
            return None

        member = (
            self.db.query(PoolMember)
            .filter(
                PoolMember.pool_id == pool_id,
                PoolMember.etf_code == etf_code,
                PoolMember.removed_at.is_(None),
            )
            .first()
        )
        if member:
            member.removed_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(pool)

        return self._to_response(pool)

    def _to_response(self, pool: ETFPools) -> PoolResponse:
        """Build a PoolResponse from an ETFPools ORM object.

        Queries active members (removed_at IS NULL) and joins with
        ETFInfo to get ETF names.
        """
        members = (
            self.db.query(PoolMember, ETFInfo.name)
            .join(ETFInfo, PoolMember.etf_code == ETFInfo.code)
            .filter(
                PoolMember.pool_id == pool.id,
                PoolMember.removed_at.is_(None),
            )
            .all()
        )

        member_responses = [
            PoolMemberResponse(
                etf_code=m.PoolMember.etf_code,
                etf_name=m.name,
                added_at=m.PoolMember.added_at,
                notes=m.PoolMember.notes,
            )
            for m in members
        ]

        return PoolResponse(
            id=pool.id,
            name=pool.name,
            description=pool.description,
            members=member_responses,
            created_at=pool.created_at,
            updated_at=pool.updated_at,
        )
