"""Favorite/watchlist business logic service.

Scope & boundaries (K16, 2026-07-04)
-----------------------------------
``UserFavorite`` 是**轻量级关注清单**，定位明确区别于平台上的其他
"标的聚合"概念，请勿在本服务中扩展任何与权重 / 仓位 / 资金相关的能力。

| 概念                | 表 / 服务                          | 用途                          |
|---------------------|-------------------------------------|-------------------------------|
| Favorites（本服务） | user_favorite                       | 快速关注 + 触发 News 聚合     |
| Pool                | etf_pools / pool_service            | 中长期目标组合（权重 / 算法）  |
| Paper Trade         | paper_trade_account / positions     | 模拟账户实际持仓               |
| Live Trade          | live_trade_config / positions       | 真实账户实际持仓               |

设计意图：
* Favorites 是「我感兴趣的标的」—— 用户随口说"加个关注"应该落到这里。
* Pool 是「我想长期持有这些、且想给它们配权重」—— 用户说"建一个目标组合"。
* 实际持仓属于"已经下过订单"的领域，跟 Favorites / Pool 都无强绑定。

如果未来要让 Favorites 一键导入到 Pool / Paper Trade，请在 **PoolService**
或 **PaperTradingService** 中新增专门的"导入"端点，不要在本服务里堆砌。
"""


from fastapi import HTTPException
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
        # Validate ETF exists
        etf = self.db.query(ETFInfo.code).filter(ETFInfo.code == etf_code).first()
        if not etf:
            raise HTTPException(status_code=404, detail="ETF not found")

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
