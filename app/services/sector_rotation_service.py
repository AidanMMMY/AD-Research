"""Sector rotation analysis service.

Provides sector performance tracking, relative strength calculation,
momentum ranking, and rotation signal detection.
"""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.etf import ETFIndicator, ETFInfo


class SectorRotationService:
    """Service for sector rotation analysis."""

    def __init__(self, db: Session):
        self.db = db

    def get_sector_list(self) -> list[dict[str, Any]]:
        """Get all ETF categories (sectors) with counts."""
        results = (
            self.db.query(
                ETFInfo.category,
                func.count(ETFInfo.code).label("count"),
            )
            .filter(ETFInfo.status == "active")
            .group_by(ETFInfo.category)
            .order_by(func.count(ETFInfo.code).desc())
            .all()
        )
        return [
            {"category": r.category, "count": r.count}
            for r in results
            if r.category
        ]

    def analyze_sectors(
        self,
        trade_date: date | None = None,
        window_weeks: int = 4,
    ) -> dict[str, Any]:
        """Analyze sector performance and rotation signals.

        Args:
            trade_date: Date to analyze. Defaults to latest available indicator date.
            window_weeks: Number of weeks for momentum calculation.

        Returns:
            Dict with sector performance, relative strength, momentum ranking,
            and rotation signals.
        """
        if trade_date is None:
            latest = self.db.query(func.max(ETFIndicator.trade_date)).scalar()
            if latest is None:
                return {"sectors": [], "market_avg": None, "rotation_signals": []}
            trade_date = latest

        # Get indicators for the latest date
        indicators = (
            self.db.query(ETFIndicator, ETFInfo)
            .join(ETFInfo, ETFIndicator.etf_code == ETFInfo.code)
            .filter(ETFIndicator.trade_date == trade_date)
            .all()
        )

        if not indicators:
            return {"sectors": [], "market_avg": None, "rotation_signals": []}

        # Calculate per-sector averages
        sector_data: dict[str, dict[str, list[float]]] = {}
        all_returns_1m: list[float] = []
        all_returns_3m: list[float] = []
        all_sharpe: list[float] = []

        for ind, info in indicators:
            cat = info.category if info.category else (info.sub_category or "其他")
            if cat not in sector_data:
                sector_data[cat] = {
                    "return_1m": [],
                    "return_3m": [],
                    "sharpe_1y": [],
                    "volatility_20d": [],
                    "rsi14": [],
                }
            if ind.return_1m is not None:
                sector_data[cat]["return_1m"].append(float(ind.return_1m))
                all_returns_1m.append(float(ind.return_1m))
            if ind.return_3m is not None:
                sector_data[cat]["return_3m"].append(float(ind.return_3m))
                all_returns_3m.append(float(ind.return_3m))
            if ind.sharpe_1y is not None:
                sector_data[cat]["sharpe_1y"].append(float(ind.sharpe_1y))
                all_sharpe.append(float(ind.sharpe_1y))
            if ind.volatility_20d is not None:
                sector_data[cat]["volatility_20d"].append(float(ind.volatility_20d))
            if ind.rsi14 is not None:
                sector_data[cat]["rsi14"].append(float(ind.rsi14))

        # Market average
        market_avg = {
            "return_1m": sum(all_returns_1m) / len(all_returns_1m) if all_returns_1m else 0,
            "return_3m": sum(all_returns_3m) / len(all_returns_3m) if all_returns_3m else 0,
            "sharpe_1y": sum(all_sharpe) / len(all_sharpe) if all_sharpe else 0,
        }

        # Build sector summary
        sectors: list[dict[str, Any]] = []
        for cat, values in sector_data.items():
            if not values["return_1m"]:
                continue
            avg_1m = sum(values["return_1m"]) / len(values["return_1m"])
            avg_3m = sum(values["return_3m"]) / len(values["return_3m"]) if values["return_3m"] else 0
            avg_sharpe = sum(values["sharpe_1y"]) / len(values["sharpe_1y"]) if values["sharpe_1y"] else 0
            avg_vol = sum(values["volatility_20d"]) / len(values["volatility_20d"]) if values["volatility_20d"] else 0
            avg_rsi = sum(values["rsi14"]) / len(values["rsi14"]) if values["rsi14"] else 50

            # Relative Strength = sector return / market average return
            rs_1m = avg_1m / market_avg["return_1m"] if market_avg["return_1m"] != 0 else 1.0
            rs_3m = avg_3m / market_avg["return_3m"] if market_avg["return_3m"] != 0 else 1.0

            sectors.append({
                "category": cat,
                "count": len(values["return_1m"]),
                "return_1m": round(avg_1m, 4),
                "return_3m": round(avg_3m, 4),
                "sharpe_1y": round(avg_sharpe, 4),
                "volatility_20d": round(avg_vol, 4),
                "rsi14": round(avg_rsi, 2),
                "relative_strength_1m": round(rs_1m, 4),
                "relative_strength_3m": round(rs_3m, 4),
            })

        # Sort by 1-month return for momentum ranking
        sectors.sort(key=lambda x: x["return_1m"], reverse=True)
        for rank, sector in enumerate(sectors, 1):
            sector["momentum_rank"] = rank

        # Rotation signals: detect sectors that moved up/down significantly in ranking
        rotation_signals = self._detect_rotation_signals(sectors, trade_date)

        return {
            "trade_date": trade_date.isoformat(),
            "sectors": sectors,
            "market_avg": market_avg,
            "rotation_signals": rotation_signals,
        }

    def _detect_rotation_signals(
        self,
        current_sectors: list[dict[str, Any]],
        trade_date: date,
    ) -> list[dict[str, Any]]:
        """Detect sector rotation signals by comparing with previous period.

        Looks at the previous week's sector ranking and identifies sectors
        that moved up or down significantly.
        """
        prev_date = trade_date - timedelta(days=7)

        # Get previous period indicators
        prev_available = (
            self.db.query(func.max(ETFIndicator.trade_date))
            .filter(ETFIndicator.trade_date <= prev_date)
            .scalar()
        )

        if prev_available is None:
            return []

        prev_indicators = (
            self.db.query(ETFIndicator, ETFInfo)
            .join(ETFInfo, ETFIndicator.etf_code == ETFInfo.code)
            .filter(ETFIndicator.trade_date == prev_available)
            .all()
        )

        if not prev_indicators:
            return []

        # Calculate previous period sector averages
        prev_sector_returns: dict[str, list[float]] = {}
        for ind, info in prev_indicators:
            cat = info.category if info.category else (info.sub_category or "其他")
            if cat not in prev_sector_returns:
                prev_sector_returns[cat] = []
            if ind.return_1m is not None:
                prev_sector_returns[cat].append(float(ind.return_1m))

        prev_avg: dict[str, float] = {}
        for cat, returns in prev_sector_returns.items():
            if returns:
                prev_avg[cat] = sum(returns) / len(returns)

        if not prev_avg:
            return []

        # Rank previous period
        prev_ranked = sorted(prev_avg.items(), key=lambda x: x[1], reverse=True)
        prev_rank_map = {cat: rank for rank, (cat, _) in enumerate(prev_ranked, 1)}

        signals = []
        for sector in current_sectors:
            cat = sector["category"]
            current_rank = sector["momentum_rank"]
            prev_rank = prev_rank_map.get(cat)

            if prev_rank is None:
                continue

            rank_change = prev_rank - current_rank  # positive = moved up

            if rank_change >= 3:
                signals.append({
                    "category": cat,
                    "type": "up",
                    "message": f"{cat} 板块排名上升 {rank_change} 位，动量增强",
                    "current_rank": current_rank,
                    "previous_rank": prev_rank,
                })
            elif rank_change <= -3:
                signals.append({
                    "category": cat,
                    "type": "down",
                    "message": f"{cat} 板块排名下降 {abs(rank_change)} 位，动量减弱",
                    "current_rank": current_rank,
                    "previous_rank": prev_rank,
                })

        return signals
