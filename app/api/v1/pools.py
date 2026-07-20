"""Pool API routes.

Provides CRUD endpoints for ETF pools, member management,
weight management, analytics, and snapshots.

M21-3: pool routes are owner-scoped — list / get / create accept the
authenticated user (injected via ``get_current_user``) and pass it to
the service layer so regular users see only their own pools + legacy
NULL-owner shared pools, while admins see every pool. Write endpoints
(update / members / weights / snapshots) enforce the same ownership
rules as delete and map violations to 403.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import (
    get_current_user,
    get_pool_enhancement_service,
    get_pool_service,
)
from app.schemas.auth import UserResponse
from app.schemas.pool import (
    PoolAnalyticsResponse,
    PoolCorrelationResponse,
    PoolCreate,
    PoolMemberCreate,
    PoolResponse,
    PoolSnapshotResponse,
    PoolUpdate,
    PoolWeightResponse,
    PoolWeightSuggestRequest,
    PoolWeightSuggestResponse,
    PoolWeightUpdateRequest,
)
from app.services.pool_enhancement_service import PoolEnhancementService
from app.services.pool_service import PoolService

router = APIRouter(dependencies=[Depends(get_current_user)])


def _raise_write_permission_error(e: PermissionError, pool_id: int) -> None:
    """Map a service-layer ``PermissionError`` to a 403 HTTPException (M21-3).

    Used by all pool write endpoints (update / members / weights /
    snapshots) so a shared system pool and someone else's pool both get a
    clear Chinese 403 instead of silently succeeding (IDOR fix).
    """
    if str(e) == "system_pool":
        raise HTTPException(
            status_code=403,
            detail=f"系统预置标的池（id={pool_id}）不可修改，请新建一个自定义池代替",
        )
    raise HTTPException(status_code=403, detail="无权修改该标的池")


# ------------------------------------------------------------------
# Pool CRUD
# ------------------------------------------------------------------

@router.get("", response_model=list[PoolResponse])
def list_pools(
    current_user: UserResponse = Depends(get_current_user),
    service: PoolService = Depends(get_pool_service),
):
    """List ETF pools visible to the current user (M21-3 owner-scoped)."""
    return service.list_pools(current_user=current_user)


@router.post("", response_model=PoolResponse, status_code=201)
def create_pool(
    data: PoolCreate,
    current_user: UserResponse = Depends(get_current_user),
    service: PoolService = Depends(get_pool_service),
):
    """Create a new ETF pool (M21-3 owner-scoped; defaults to caller)."""
    return service.create_pool(data, current_user=current_user)


@router.get("/{pool_id}", response_model=PoolResponse)
def get_pool(
    pool_id: int,
    current_user: UserResponse = Depends(get_current_user),
    service: PoolService = Depends(get_pool_service),
):
    """Get a single pool by ID (M21-3 owner-scoped; 404 if not visible)."""
    pool = service.get_pool(pool_id, current_user=current_user)
    if not pool:
        raise HTTPException(status_code=404, detail=f"Pool {pool_id} not found")
    return pool


@router.put("/{pool_id}", response_model=PoolResponse)
def update_pool(
    pool_id: int,
    data: PoolUpdate,
    current_user: UserResponse = Depends(get_current_user),
    service: PoolService = Depends(get_pool_service),
):
    """Update an existing pool (M21-3 owner-scoped; 403 if not writable)."""
    try:
        pool = service.update_pool(pool_id, data, current_user=current_user)
    except PermissionError as e:
        _raise_write_permission_error(e, pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail=f"Pool {pool_id} not found")
    return pool


@router.delete("/{pool_id}", status_code=204)
def delete_pool(
    pool_id: int,
    current_user: UserResponse = Depends(get_current_user),
    service: PoolService = Depends(get_pool_service),
):
    """Delete a pool by ID (M21-3 owner-scoped).

    Status codes:
      - 204: deleted
      - 403: pool exists but is shared/legacy (``user_id IS NULL``) or
             owned by another user
      - 404: pool does not exist or already deleted
    """
    try:
        deleted = service.delete_pool(pool_id, current_user=current_user)
    except PermissionError as e:
        if str(e) == "system_pool":
            raise HTTPException(
                status_code=403,
                detail=f"系统预置标的池（id={pool_id}）不可删除，请新建一个自定义池代替",
            )
        raise HTTPException(status_code=403, detail="无权删除该标的池")
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Pool {pool_id} not found")
    return None


# ------------------------------------------------------------------
# Pool members
# ------------------------------------------------------------------

@router.post("/{pool_id}/members", response_model=PoolResponse)
def add_member(
    pool_id: int,
    data: PoolMemberCreate,
    current_user: UserResponse = Depends(get_current_user),
    service: PoolService = Depends(get_pool_service),
):
    """Add an ETF to a pool (M21-3 owner-scoped; 403 if not writable)."""
    try:
        pool = service.add_member(pool_id, data, current_user=current_user)
    except PermissionError as e:
        _raise_write_permission_error(e, pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail=f"Pool {pool_id} not found")
    return pool


@router.delete("/{pool_id}/members/{etf_code}", response_model=PoolResponse)
def remove_member(
    pool_id: int,
    etf_code: str,
    current_user: UserResponse = Depends(get_current_user),
    service: PoolService = Depends(get_pool_service),
):
    """Remove an ETF from a pool (soft delete; M21-3 owner-scoped)."""
    try:
        pool = service.remove_member(pool_id, etf_code, current_user=current_user)
    except PermissionError as e:
        _raise_write_permission_error(e, pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail=f"Pool {pool_id} not found")
    return pool


# ------------------------------------------------------------------
# Pool weights
# ------------------------------------------------------------------

@router.get("/{pool_id}/weights", response_model=list[PoolWeightResponse])
def get_pool_weights(
    pool_id: int,
    service: PoolEnhancementService = Depends(get_pool_enhancement_service),
):
    """Get all weight configurations for a pool."""
    return service.get_weights(pool_id)


@router.put("/{pool_id}/weights/{etf_code}", response_model=PoolWeightResponse)
def update_pool_weight(
    pool_id: int,
    etf_code: str,
    data: PoolWeightUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    service: PoolEnhancementService = Depends(get_pool_enhancement_service),
):
    """Update the target weight for an ETF in a pool (M21-3 owner-scoped)."""
    try:
        result = service.update_weight(
            pool_id, etf_code, data.target_weight, current_user=current_user
        )
    except PermissionError as e:
        _raise_write_permission_error(e, pool_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Pool {pool_id} not found")
    return result


@router.post("/{pool_id}/weights/suggest", response_model=list[PoolWeightSuggestResponse])
def suggest_pool_weights(
    pool_id: int,
    data: PoolWeightSuggestRequest,
    current_user: UserResponse = Depends(get_current_user),
    service: PoolEnhancementService = Depends(get_pool_enhancement_service),
):
    """Generate suggested weights for pool members using an algorithm.

    Supported algorithms: equal, score, risk_parity.
    (M21-3 owner-scoped; 403 if the pool is not writable by the caller.)
    """
    try:
        return service.suggest_weights(
            pool_id,
            algorithm=data.algorithm,
            template_id=data.template_id,
            current_user=current_user,
        )
    except PermissionError as e:
        _raise_write_permission_error(e, pool_id)


# ------------------------------------------------------------------
# Pool analytics
# ------------------------------------------------------------------

@router.get("/{pool_id}/analytics", response_model=PoolAnalyticsResponse)
def get_pool_analytics(
    pool_id: int,
    service: PoolEnhancementService = Depends(get_pool_enhancement_service),
):
    """Get comprehensive analytics for a pool."""
    analytics = service.get_analytics(pool_id)
    if not analytics:
        raise HTTPException(status_code=404, detail=f"Pool {pool_id} not found")
    return analytics


@router.get("/{pool_id}/correlation", response_model=PoolCorrelationResponse)
def get_pool_correlation(
    pool_id: int,
    service: PoolEnhancementService = Depends(get_pool_enhancement_service),
):
    """Get correlation matrix for pool members based on daily returns."""
    result = service.get_correlation_matrix(pool_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Pool {pool_id} not found or empty")
    return result


# ------------------------------------------------------------------
# Pool snapshots
# ------------------------------------------------------------------

@router.get("/{pool_id}/snapshots", response_model=list[PoolSnapshotResponse])
def get_pool_snapshots(
    pool_id: int,
    limit: int = 10,
    service: PoolEnhancementService = Depends(get_pool_enhancement_service),
):
    """Get recent snapshots for a pool."""
    return service.get_snapshots(pool_id, limit=limit)


@router.post("/{pool_id}/snapshots", response_model=PoolSnapshotResponse)
def create_pool_snapshot(
    pool_id: int,
    snapshot_date: date | None = None,
    current_user: UserResponse = Depends(get_current_user),
    service: PoolEnhancementService = Depends(get_pool_enhancement_service),
):
    """Create a snapshot of pool data for a given date (M21-3 owner-scoped)."""
    try:
        result = service.create_snapshot(
            pool_id, snapshot_date=snapshot_date, current_user=current_user
        )
    except PermissionError as e:
        _raise_write_permission_error(e, pool_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Pool {pool_id} not found")
    return result
