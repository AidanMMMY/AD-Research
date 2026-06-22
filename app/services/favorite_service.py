"""Favorite/watchlist business logic service."""


from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.etf import ETFInfo
from app.models.favorite import UserFavorite
from app.schemas.favorite import FavoriteItem, FavoriteListResponse


class FavoriteService:
    """Service for managing user favorite ETFs."""

    def __init__(self, db: Session):
        self.db = db

    def _make_id(self, username: str, etf_code: str) -> str:
        """Generate composite primary key."""
        return f"{username}_{etf_code}"

    def list_favorites(self, username: str, limit: int = 50) -> FavoriteListResponse:
        """Get user's favorite ETFs, ordered by most recently added."""
        results = (
            self.db.query(UserFavorite, ETFInfo)
            .join(ETFInfo, UserFavorite.etf_code == ETFInfo.code)
            .filter(UserFavorite.username == username)
            .order_by(desc(UserFavorite.created_at))
            .limit(limit)
            .all()
        )

        items = [
            FavoriteItem(
                etf_code=fav.etf_code,
                etf_name=etf.name if etf else None,
                category=etf.category if etf else None,
                market=etf.market if etf else None,
                created_at=fav.created_at,
            )
            for fav, etf in results
        ]

        return FavoriteListResponse(items=items, count=len(items))

    def is_favorite(self, username: str, etf_code: str) -> bool:
        """Check if an ETF is in user's favorites."""
        exists = (
            self.db.query(UserFavorite)
            .filter(
                UserFavorite.id == self._make_id(username, etf_code),
                UserFavorite.username == username,
            )
            .first()
        )
        return exists is not None

    def toggle_favorite(self, username: str, etf_code: str) -> bool:
        """Toggle favorite status. Returns True if added, False if removed."""
        fav_id = self._make_id(username, etf_code)
        existing = (
            self.db.query(UserFavorite)
            .filter(UserFavorite.id == fav_id)
            .first()
        )

        if existing:
            self.db.delete(existing)
            self.db.commit()
            return False
        else:
            fav = UserFavorite(
                id=fav_id,
                username=username,
                etf_code=etf_code,
            )
            self.db.add(fav)
            self.db.commit()
            return True

    def add_favorite(self, username: str, etf_code: str) -> bool:
        """Add an ETF to favorites. Returns True if added, False if already exists."""
        fav_id = self._make_id(username, etf_code)
        existing = (
            self.db.query(UserFavorite)
            .filter(UserFavorite.id == fav_id)
            .first()
        )
        if existing:
            return False

        fav = UserFavorite(
            id=fav_id,
            username=username,
            etf_code=etf_code,
        )
        self.db.add(fav)
        self.db.commit()
        return True

    def remove_favorite(self, username: str, etf_code: str) -> bool:
        """Remove an ETF from favorites. Returns True if removed, False if not found."""
        fav_id = self._make_id(username, etf_code)
        existing = (
            self.db.query(UserFavorite)
            .filter(UserFavorite.id == fav_id)
            .first()
        )
        if existing:
            self.db.delete(existing)
            self.db.commit()
            return True
        return False
