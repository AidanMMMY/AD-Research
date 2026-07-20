"""ETF pool business logic service.

Provides CRUD operations for ETF pools and member management
with soft-delete support.

M21-3: Pools are now owner-scoped. ``list_pools`` accepts an optional
``current_user`` (admin users see all pools; regular users see their own
pools + legacy NULL-owner shared pools). ``get_pool`` enforces the same
visibility rule. ``create_pool`` defaults ``user_id`` to the caller's id
when not provided in the request body.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session, selectinload

from app.models.pool import ETFPools, PoolMember, PoolWeight
from app.schemas.auth import UserResponse
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

    def list_pools(
        self, current_user: UserResponse | None = None
    ) -> list[PoolResponse]:
        """List active pools the current user is allowed to see.

        Visibility rule (M21-3 owner-scoping):
          - admin → every active pool
          - regular user → pools owned by them + pools with ``user_id IS NULL``
            (treated as shared/legacy pools, kept visible to every user)

        Uses ``selectinload`` so each pool's members + their joined
        ETFInfo rows are fetched in two batched SELECTs (instead of
        one query per pool inside ``_to_response``).
        """
        q = (
            self.db.query(ETFPools)
            .options(
                selectinload(ETFPools.members).selectinload(PoolMember.etf_info)
            )
            .filter(ETFPools.deleted_at.is_(None))
        )
        if current_user is not None and current_user.role != "admin":
            q = q.filter(
                (ETFPools.user_id == current_user.id)
                | (ETFPools.user_id.is_(None))
            )
        pools = q.all()
        return [self._to_response(pool) for pool in pools]

    def get_pool(
        self,
        pool_id: int,
        current_user: UserResponse | None = None,
    ) -> PoolResponse | None:
        """Get a single active pool by ID, respecting owner-scoping."""
        q = (
            self.db.query(ETFPools)
            .options(
                selectinload(ETFPools.members).selectinload(PoolMember.etf_info)
            )
            .filter(ETFPools.id == pool_id)
            .filter(ETFPools.deleted_at.is_(None))
        )
        if current_user is not None and current_user.role != "admin":
            q = q.filter(
                (ETFPools.user_id == current_user.id)
                | (ETFPools.user_id.is_(None))
            )
        pool = q.first()
        return self._to_response(pool) if pool else None

    def create_pool(
        self,
        data: PoolCreate,
        current_user: UserResponse | None = None,
    ) -> PoolResponse:
        """Create a new pool.

        ``user_id`` defaults to the caller's id (when authenticated). If the
        client sent ``user_id`` explicitly we honour it for admin tools.
        """
        owner_id = data.user_id
        if owner_id is None and current_user is not None:
            owner_id = current_user.id
        pool = ETFPools(
            name=data.name,
            description=data.description,
            user_id=owner_id,
        )
        self.db.add(pool)
        self.db.commit()
        self.db.refresh(pool)
        return self._to_response(pool)

    def _assert_write_access(self, pool: ETFPools, current_user: UserResponse | None) -> None:
        """Enforce owner-scoped write access (same rules as ``delete_pool``).

        ``current_user=None`` means an internal/unscoped caller and skips
        the check (same convention as ``list_pools`` / ``get_pool``).
        Raises ``PermissionError("system_pool")`` for NULL-owner shared
        pools and ``PermissionError("not_owner")`` for pools owned by
        another user.
        """
        if current_user is None:
            return
        is_admin = current_user.role == "admin"
        if not is_admin and pool.user_id is None:
            raise PermissionError("system_pool")
        if not is_admin and pool.user_id != current_user.id:
            raise PermissionError("not_owner")

    def update_pool(
        self,
        pool_id: int,
        data: PoolUpdate,
        current_user: UserResponse | None = None,
    ) -> PoolResponse | None:
        """Update an existing active pool (owner-scoped, M21-3)."""
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
        self._assert_write_access(pool, current_user)

        if data.name is not None:
            pool.name = data.name
        if data.description is not None:
            pool.description = data.description

        self.db.commit()
        self.db.refresh(pool)
        return self._to_response(pool)

    def delete_pool(
        self, pool_id: int, current_user: UserResponse | None = None
    ) -> bool:
        """Soft-delete a pool, respecting owner-scoping (M21-3).

        Behaviour matrix:
          - admin                → can delete any active pool.
          - regular user, owned  → can delete (returns True, sets deleted_at).
          - regular user, NULL   → cannot delete (raises PermissionError("system_pool")).
          - regular user, other  → cannot delete (raises PermissionError("not_owner")).
          - already deleted/missing → returns False (caller maps to 404).

        Previously (review-pool-bug) the ownership filter excluded
        ``user_id IS NULL`` rows so non-admins silently hit a 404
        ("Pool 1 not found") on seeded system pools. The 3-way check
        below fixes that by surfacing a 403 with a clear Chinese message
        from the API layer.
        """
        pool = (
            self.db.query(ETFPools)
            .filter(ETFPools.id == pool_id)
            .filter(ETFPools.deleted_at.is_(None))
            .first()
        )
        if not pool:
            return False

        is_admin = current_user is not None and current_user.role == "admin"
        if not is_admin and pool.user_id is None:
            raise PermissionError("system_pool")
        if not is_admin and pool.user_id != current_user.id:
            raise PermissionError("not_owner")

        pool.deleted_at = datetime.now(UTC)
        self.db.commit()
        return True

    def add_member(
        self,
        pool_id: int,
        data: PoolMemberCreate,
        current_user: UserResponse | None = None,
    ) -> PoolResponse | None:
        """Add an ETF to an active pool (owner-scoped, M21-3)."""
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
        self._assert_write_access(pool, current_user)

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
        self,
        pool_id: int,
        etf_code: str,
        current_user: UserResponse | None = None,
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
        self._assert_write_access(pool, current_user)

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
            user_id=pool.user_id,
            members=member_responses,
            created_at=pool.created_at,
            updated_at=pool.updated_at,
        )
