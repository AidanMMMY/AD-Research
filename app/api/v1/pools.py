"""Pool API routes.

Provides CRUD endpoints for ETF pools, member management,
weight management, analytics, and snapshots.
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_pool_enhancement_service, get_pool_service
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

router = APIRouter()


# ------------------------------------------------------------------
# Pool CRUD
# ------------------------------------------------------------------

@router.get("", response_model=list[PoolResponse])
def list_pools(service: PoolService = Depends(get_pool_service)):
    """List all ETF pools with their active members."""
    return service.list_pools()


@router.post("", response_model=PoolResponse, status_code=201)
def create_pool(data: PoolCreate, service: PoolService = Depends(get_pool_service)):
    """Create a new ETF pool."""
    return service.create_pool(data)


@router.get("/{pool_id}", response_model=PoolResponse)
def get_pool(pool_id: int, service: PoolService = Depends(get_pool_service)):
    """Get a single pool by ID."""
    pool = service.get_pool(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail=f"Pool {pool_id} not found")
    return pool


@router.put("/{pool_id}", response_model=PoolResponse)
def update_pool(
    pool_id: int,
    data: PoolUpdate,
    service: PoolService = Depends(get_pool_service),
):
    """Update an existing pool."""
    pool = service.update_pool(pool_id, data)
    if not pool:
        raise HTTPException(status_code=404, detail=f"Pool {pool_id} not found")
    return pool


@router.delete("/{pool_id}", status_code=204)
def delete_pool(pool_id: int, service: PoolService = Depends(get_pool_service)):
    """Delete a pool by ID."""
    deleted = service.delete_pool(pool_id)
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
    service: PoolService = Depends(get_pool_service),
):
    """Add an ETF to a pool."""
    pool = service.add_member(pool_id, data)
    if not pool:
        raise HTTPException(status_code=404, detail=f"Pool {pool_id} not found")
    return pool


@router.delete("/{pool_id}/members/{etf_code}", response_model=PoolResponse)
def remove_member(
    pool_id: int,
    etf_code: str,
    service: PoolService = Depends(get_pool_service),
):
    """Remove an ETF from a pool (soft delete)."""
    pool = service.remove_member(pool_id, etf_code)
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
    service: PoolEnhancementService = Depends(get_pool_enhancement_service),
):
    """Update the target weight for an ETF in a pool."""
    result = service.update_weight(pool_id, etf_code, data.target_weight)
    if not result:
        raise HTTPException(status_code=404, detail=f"Pool {pool_id} not found")
    return result


@router.post("/{pool_id}/weights/suggest", response_model=list[PoolWeightSuggestResponse])
def suggest_pool_weights(
    pool_id: int,
    data: PoolWeightSuggestRequest,
    service: PoolEnhancementService = Depends(get_pool_enhancement_service),
):
    """Generate suggested weights for pool members using an algorithm.

    Supported algorithms: equal, score, risk_parity.
    """
    return service.suggest_weights(
        pool_id, algorithm=data.algorithm, template_id=data.template_id
    )


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
    snapshot_date: Optional[date] = None,
    service: PoolEnhancementService = Depends(get_pool_enhancement_service),
):
    """Create a snapshot of pool data for a given date."""
    result = service.create_snapshot(pool_id, snapshot_date=snapshot_date)
    if not result:
        raise HTTPException(status_code=404, detail=f"Pool {pool_id} not found")
    return result
