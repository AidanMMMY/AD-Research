"""Favorite Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FavoriteItem(BaseModel):
    """A favorite ETF item with basic info."""

    model_config = ConfigDict(from_attributes=True)

    etf_code: str
    etf_name: str | None = None
    category: str | None = None
    market: str | None = None
    created_at: datetime | None = None


class FavoriteListResponse(BaseModel):
    """List of user's favorite ETFs."""

    items: list[FavoriteItem]
    count: int


class FavoriteToggleResponse(BaseModel):
    """Toggle favorite response."""

    etf_code: str
    is_favorite: bool
    message: str


class FavoriteStatusResponse(BaseModel):
    """Check if an ETF is favorited."""

    etf_code: str
    is_favorite: bool
