"""User favorite/watchlist API routes."""


from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_favorite_service
from app.schemas.favorite import (
    FavoriteListResponse,
    FavoriteStatusResponse,
    FavoriteToggleResponse,
)
from app.services.favorite_service import FavoriteService

router = APIRouter()


@router.get("", response_model=FavoriteListResponse)
def list_favorites(
    limit: int = 50,
    service: FavoriteService = Depends(get_favorite_service),
    user=Depends(get_current_user),
):
    """Get current user's favorite ETFs."""
    return service.list_favorites(username=user.username, limit=limit)


@router.get("/{etf_code}/status", response_model=FavoriteStatusResponse)
def check_favorite(
    etf_code: str,
    service: FavoriteService = Depends(get_favorite_service),
    user=Depends(get_current_user),
):
    """Check if an ETF is in user's favorites."""
    is_fav = service.is_favorite(username=user.username, etf_code=etf_code)
    return FavoriteStatusResponse(etf_code=etf_code, is_favorite=is_fav)


@router.post("/{etf_code}/toggle", response_model=FavoriteToggleResponse)
def toggle_favorite(
    etf_code: str,
    service: FavoriteService = Depends(get_favorite_service),
    user=Depends(get_current_user),
):
    """Toggle favorite status for an ETF."""
    added = service.toggle_favorite(username=user.username, etf_code=etf_code)
    return FavoriteToggleResponse(
        etf_code=etf_code,
        is_favorite=added,
        message="已添加收藏" if added else "已取消收藏",
    )


@router.post("/{etf_code}/add", response_model=FavoriteToggleResponse)
def add_favorite(
    etf_code: str,
    service: FavoriteService = Depends(get_favorite_service),
    user=Depends(get_current_user),
):
    """Add an ETF to favorites."""
    added = service.add_favorite(username=user.username, etf_code=etf_code)
    return FavoriteToggleResponse(
        etf_code=etf_code,
        is_favorite=added,
        message="已添加收藏" if added else "已在收藏中",
    )


@router.delete("/{etf_code}", response_model=FavoriteToggleResponse)
def remove_favorite(
    etf_code: str,
    service: FavoriteService = Depends(get_favorite_service),
    user=Depends(get_current_user),
):
    """Remove an ETF from favorites."""
    removed = service.remove_favorite(username=user.username, etf_code=etf_code)
    return FavoriteToggleResponse(
        etf_code=etf_code,
        is_favorite=not removed,
        message="已取消收藏" if removed else "未在收藏中",
    )
