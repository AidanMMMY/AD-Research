"""ETF pool business logic service.

Provides CRUD operations for ETF pools and member management
with soft-delete support.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session, selectinload

from app.models.pool import ETFPools, PoolMember, PoolWeight
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

    def list_pools(self) -> list[PoolResponse]:
        """List all active pools with their active members.

        Uses ``selectinload`` so each pool's members + their joined
        ETFInfo rows are fetched in two batched SELECTs (instead of
        one query per pool inside ``_to_response``). This eliminates
        the N+1 query pattern of the previous implementation.
        """
        pools = (
            self.db.query(ETFPools)
            .options(
                selectinload(ETFPools.members).selectinload(PoolMember.etf_info)
            )
            .filter(ETFPools.deleted_at.is_(None))
            .all()
        )
        return [self._to_response(pool) for pool in pools]

    def get_pool(self, pool_id: int) -> PoolResponse | None:
        """Get a single active pool by ID."""
        pool = (
            self.db.query(ETFPools)
            .options(
                selectinload(ETFPools.members).selectinload(PoolMember.etf_info)
            )
            .filter(ETFPools.id == pool_id)
            .filter(ETFPools.deleted_at.is_(None))
            .first()
        )
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
    ) -> PoolResponse | None:
        """Update an existing active pool."""
        pool = (
            self.db.query(ETFPools)
            .options(
                selectinload(ETFPools.members).selectinload(PoolMember.etf_info)
            )
            .filter(ETFPools.id == pool_id)
            .filter(ETFPools.deleted_at.is_(None))
            .first()
        )
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
        """Soft-delete a pool."""
        pool = (
            self.db.query(ETFPools)
            .filter(ETFPools.id == pool_id)
            .filter(ETFPools.deleted_at.is_(None))
            .first()
        )
        if not pool:
            return False

        pool.deleted_at = datetime.now(UTC)
        self.db.commit()
        return True

    def add_member(
        self, pool_id: int, data: PoolMemberCreate
    ) -> PoolResponse | None:
        """Add an ETF to an active pool."""
        pool = (
            self.db.query(ETFPools)
            .options(
                selectinload(ETFPools.members).selectinload(PoolMember.etf_info)
            )
            .filter(ETFPools.id == pool_id)
            .filter(ETFPools.deleted_at.is_(None))
            .with_for_update()
            .first()
        )
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
            .with_for_update()
            .first()
        )
        if existing:
            # Already an active member, just return the pool
            return self._to_response(pool)

        member = PoolMember(
            pool_id=pool_id, etf_code=data.etf_code, notes=data.notes
        )
        self.db.add(member)

        # Also create a default weight record for this member
        weight = PoolWeight(
            pool_id=pool_id,
            etf_code=data.etf_code,
            target_weight=0.0,
            weight_source="manual"
        )
        self.db.add(weight)

        self.db.commit()
        self.db.refresh(pool)
        return self._to_response(pool)

    def remove_member(
        self, pool_id: int, etf_code: str
    ) -> PoolResponse | None:
        """Soft-remove an ETF from a pool and clear its weight records."""
        pool = (
            self.db.query(ETFPools)
            .options(
                selectinload(ETFPools.members).selectinload(PoolMember.etf_info)
            )
            .filter(ETFPools.id == pool_id)
            .filter(ETFPools.deleted_at.is_(None))
            .with_for_update()
            .first()
        )
        if not pool:
            return None

        member = (
            self.db.query(PoolMember)
            .filter(
                PoolMember.pool_id == pool_id,
                PoolMember.etf_code == etf_code,
                PoolMember.removed_at.is_(None),
            )
            .with_for_update()
            .first()
        )
        if member:
            member.removed_at = datetime.now(UTC)
            # Soft-delete weight records for the removed member so they do not
            # leak into analytics or the UI, while preserving history.
            self.db.query(PoolWeight).filter(
                PoolWeight.pool_id == pool_id,
                PoolWeight.etf_code == etf_code,
                PoolWeight.removed_at.is_(None),
            ).update({"removed_at": datetime.now(UTC)})
            self.db.commit()
            self.db.refresh(pool)

        return self._to_response(pool)

    def _to_response(self, pool: ETFPools) -> PoolResponse:
        """Build a PoolResponse from an ETFPools ORM object.

        Reads members and their ETFInfo from the eagerly-loaded
        ``pool.members`` relationship so this method issues no
        additional queries. Only currently-active members
        (``removed_at IS NULL``) are included in the response.
        """
        member_responses = [
            PoolMemberResponse(
                etf_code=m.etf_code,
                etf_name=m.etf_info.name if m.etf_info is not None else None,
                name_zh=m.etf_info.name_zh if m.etf_info is not None else None,
                added_at=m.added_at,
                notes=m.notes,
            )
            for m in pool.members
            if m.removed_at is None
        ]

        return PoolResponse(
            id=pool.id,
            name=pool.name,
            description=pool.description,
            members=member_responses,
            created_at=pool.created_at,
            updated_at=pool.updated_at,
        )
