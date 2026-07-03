"""Pool enhancement business logic service.

Provides weight management, analytics, correlation analysis, and snapshot
operations for ETF pools.
"""

from datetime import date
from typing import Any

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.etf import ETFIndicator, ETFInfo
from app.models.pool import ETFPools, PoolMember, PoolSnapshot, PoolWeight
from app.models.scoring import ETFScore


class PoolEnhancementService:
    """Service for pool enhancement operations."""

    REBALANCE_THRESHOLD = 0.10  # 10% deviation triggers rebalance alert

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Weight management
    # ------------------------------------------------------------------

    def get_weights(self, pool_id: int) -> list[dict[str, Any]]:
        """Get all weight configurations for active members of a pool.

        Returns a list of weight dicts with ETF metadata, including
        both target_weight and suggested_weight. Removed members are excluded.

        Uses an outer join from PoolMember so active members that do not yet
        have a PoolWeight row (e.g. members added before the auto-weight
        creation fix) still appear in the table with default zero weights.
        """
        rows = (
            self.db.query(PoolMember, PoolWeight, ETFInfo.name)
            .outerjoin(
                PoolWeight,
                (PoolMember.etf_code == PoolWeight.etf_code)
                & (PoolMember.pool_id == PoolWeight.pool_id)
                & (PoolWeight.removed_at.is_(None)),
            )
            .join(ETFInfo, PoolMember.etf_code == ETFInfo.code)
            .filter(PoolMember.pool_id == pool_id)
            .filter(PoolMember.removed_at.is_(None))
            .all()
        )

        return [
            {
                "etf_code": member.etf_code,
                "etf_name": name,
                "target_weight": float(weight.target_weight) if weight is not None and weight.target_weight is not None else 0.0,
                "suggested_weight": float(weight.suggested_weight) if weight is not None and weight.suggested_weight is not None else None,
                "weight_source": weight.weight_source if weight is not None else "manual",
                "updated_at": weight.updated_at if weight is not None else None,
            }
            for member, weight, name in rows
        ]

    def update_weight(
        self, pool_id: int, etf_code: str, target_weight: float
    ) -> dict[str, Any] | None:
        """Update the target weight for an active ETF in a pool.

        Creates a new weight record if one doesn't exist. Returns None if
        the ETF is not an active member of the pool. Rejects negative weights
        or weights that would push the pool total above 100%.
        """
        if target_weight < 0 or target_weight > 100:
            raise ValueError("target_weight must be between 0 and 100")

        # Only allow weight updates for active members
        member = (
            self.db.query(PoolMember)
            .filter(
                PoolMember.pool_id == pool_id,
                PoolMember.etf_code == etf_code,
                PoolMember.removed_at.is_(None),
            )
            .first()
        )
        if not member:
            return None

        # Calculate current total weight for active weights in this pool,
        # excluding the ETF being updated.
        other_total = (
            self.db.query(func.coalesce(func.sum(PoolWeight.target_weight), 0))
            .filter(
                PoolWeight.pool_id == pool_id,
                PoolWeight.etf_code != etf_code,
                PoolWeight.removed_at.is_(None),
            )
            .scalar()
        ) or 0

        new_total = float(other_total) + target_weight
        if new_total > 100.01:
            raise ValueError(
                f"Pool weight total would be {new_total:.2f}%; must not exceed 100%"
            )

        weight = (
            self.db.query(PoolWeight)
            .filter(
                PoolWeight.pool_id == pool_id,
                PoolWeight.etf_code == etf_code,
                PoolWeight.removed_at.is_(None),
            )
            .first()
        )

        if weight:
            weight.target_weight = target_weight
            weight.weight_source = "manual"
        else:
            weight = PoolWeight(
                pool_id=pool_id,
                etf_code=etf_code,
                target_weight=target_weight,
                weight_source="manual",
            )
            self.db.add(weight)

        self.db.commit()
        self.db.refresh(weight)

        # Get ETF name
        etf = self.db.query(ETFInfo).filter(ETFInfo.code == etf_code).first()
        return {
            "etf_code": weight.etf_code,
            "etf_name": etf.name if etf else None,
            "target_weight": float(weight.target_weight) if weight.target_weight is not None else 0.0,
            "suggested_weight": float(weight.suggested_weight) if weight.suggested_weight is not None else None,
            "weight_source": weight.weight_source,
            "updated_at": weight.updated_at,
        }

    def suggest_weights(
        self,
        pool_id: int,
        algorithm: str = "equal",
        template_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Generate suggested weights for pool members using an algorithm.

        Args:
            pool_id: The pool ID.
            algorithm: One of "equal", "score", "risk_parity".
            template_id: Score template ID (required for "score" algorithm).

        Returns:
            List of weight suggestion dicts.
        """
        members = self._get_active_members(pool_id)
        if not members:
            return []

        codes = [m.etf_code for m in members]

        if algorithm == "equal":
            suggestions = self._suggest_by_equal(codes)
        elif algorithm == "score":
            suggestions = self._suggest_by_score(codes, template_id)
        elif algorithm == "risk_parity":
            suggestions = self._suggest_by_risk_parity(codes)
        else:
            suggestions = self._suggest_by_equal(codes)

        # Store suggestions in the database (only for active weight records)
        for suggestion in suggestions:
            weight = (
                self.db.query(PoolWeight)
                .filter(
                    PoolWeight.pool_id == pool_id,
                    PoolWeight.etf_code == suggestion["etf_code"],
                    PoolWeight.removed_at.is_(None),
                )
                .first()
            )
            if weight:
                weight.suggested_weight = suggestion["suggested_weight"]
                weight.weight_source = algorithm
            else:
                weight = PoolWeight(
                    pool_id=pool_id,
                    etf_code=suggestion["etf_code"],
                    suggested_weight=suggestion["suggested_weight"],
                    weight_source=algorithm,
                )
                self.db.add(weight)

        self.db.commit()
        return suggestions

    def _suggest_by_equal(self, codes: list[str]) -> list[dict[str, Any]]:
        """Suggest equal weights for all members."""
        n = len(codes)
        weight = round(100.0 / n, 2)
        # Adjust last one to ensure sum = 100
        weights = [weight] * n
        weights[-1] = round(100.0 - sum(weights[:-1]), 2)

        etf_names = {
            e.code: e.name
            for e in self.db.query(ETFInfo).filter(ETFInfo.code.in_(codes)).all()
        }

        return [
            {
                "etf_code": code,
                "etf_name": etf_names.get(code),
                "suggested_weight": w,
                "algorithm": "equal",
            }
            for code, w in zip(codes, weights, strict=False)
        ]

    def _suggest_by_score(
        self, codes: list[str], template_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Suggest weights proportional to composite scores."""
        # Get latest scores for the codes
        if template_id is None:
            latest_score_date = self.db.query(
                func.max(ETFScore.trade_date)
            ).scalar()
        else:
            latest_score_date = self.db.query(
                func.max(ETFScore.trade_date)
            ).filter(ETFScore.template_id == template_id).scalar()

        query = self.db.query(ETFScore).filter(ETFScore.etf_code.in_(codes))
        if latest_score_date:
            query = query.filter(ETFScore.trade_date == latest_score_date)
        if template_id:
            query = query.filter(ETFScore.template_id == template_id)

        scores = query.all()
        score_map = {s.etf_code: float(s.composite_score) if s.composite_score else 0 for s in scores}

        # For codes without scores, assign average
        avg_score = sum(score_map.values()) / len(score_map) if score_map else 50.0
        for code in codes:
            if code not in score_map:
                score_map[code] = avg_score

        total_score = sum(score_map.values())
        if total_score == 0:
            return self._suggest_by_equal(codes)

        raw_weights = {code: score_map[code] / total_score * 100 for code in codes}
        # Round and adjust last to sum to 100
        rounded = {code: round(w, 2) for code, w in raw_weights.items()}
        diff = 100.0 - sum(rounded.values())
        if codes:
            rounded[codes[-1]] = round(rounded[codes[-1]] + diff, 2)

        etf_names = {
            e.code: e.name
            for e in self.db.query(ETFInfo).filter(ETFInfo.code.in_(codes)).all()
        }

        return [
            {
                "etf_code": code,
                "etf_name": etf_names.get(code),
                "suggested_weight": rounded[code],
                "algorithm": "score",
            }
            for code in codes
        ]

    def _suggest_by_risk_parity(self, codes: list[str]) -> list[dict[str, Any]]:
        """Suggest weights inversely proportional to volatility (risk parity).

        Higher volatility gets lower weight. Uses 20-day volatility from
        the latest indicator data (stored as decimal, e.g. 0.20 ≈ 20%).
        """
        indicators = self._get_latest_indicators(codes)
        vol_map = {}
        for ind in indicators:
            vol = float(ind.volatility_20d) if ind.volatility_20d else 0.20
            if vol <= 0:
                vol = 0.20
            vol_map[ind.etf_code] = vol

        # Default volatility for missing data
        avg_vol = sum(vol_map.values()) / len(vol_map) if vol_map else 0.20
        for code in codes:
            if code not in vol_map:
                vol_map[code] = avg_vol

        # Inverse volatility weighting
        inv_vols = {code: 1.0 / vol_map[code] for code in codes}
        total_inv = sum(inv_vols.values())

        raw_weights = {code: inv_vols[code] / total_inv * 100 for code in codes}
        rounded = {code: round(w, 2) for code, w in raw_weights.items()}
        diff = 100.0 - sum(rounded.values())
        if codes:
            rounded[codes[-1]] = round(rounded[codes[-1]] + diff, 2)

        etf_names = {
            e.code: e.name
            for e in self.db.query(ETFInfo).filter(ETFInfo.code.in_(codes)).all()
        }

        return [
            {
                "etf_code": code,
                "etf_name": etf_names.get(code),
                "suggested_weight": rounded[code],
                "algorithm": "risk_parity",
            }
            for code in codes
        ]

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def get_analytics(self, pool_id: int) -> dict[str, Any] | None:
        """Get comprehensive analytics for a pool.

        Returns members, category distribution, weighted performance,
        and rebalance alerts.
        """
        pool = (
            self.db.query(ETFPools)
            .filter(ETFPools.id == pool_id)
            .filter(ETFPools.deleted_at.is_(None))
            .first()
        )
        if not pool:
            return None

        members = self._get_active_members(pool_id)
        if not members:
            return {
                "pool_id": pool_id,
                "pool_name": pool.name,
                "member_count": 0,
                "members": [],
                "category_distribution": {},
                "performance": {},
                "rebalance_needed": False,
                "rebalance_alerts": [],
            }

        codes = [m.etf_code for m in members]

        # Get weights (active only)
        weights = (
            self.db.query(PoolWeight)
            .filter(
                PoolWeight.pool_id == pool_id,
                PoolWeight.etf_code.in_(codes),
                PoolWeight.removed_at.is_(None),
            )
            .all()
        )
        weight_map = {w.etf_code: float(w.target_weight) if w.target_weight else 0 for w in weights}

        # Default equal weights if no weights configured
        if not weight_map or all(w == 0 for w in weight_map.values()):
            equal_w = 100.0 / len(codes)
            weight_map = {code: equal_w for code in codes}

        # Get ETF info
        etf_info = (
            self.db.query(ETFInfo)
            .filter(ETFInfo.code.in_(codes))
            .all()
        )
        etf_name_map = {e.code: e.name for e in etf_info}
        etf_cat_map = {e.code: e.category for e in etf_info}

        # Get latest indicators
        indicators = self._get_latest_indicators(codes)

        # Build member list
        member_list = []
        for m in members:
            member_list.append({
                "etf_code": m.etf_code,
                "etf_name": etf_name_map.get(m.etf_code),
                "category": etf_cat_map.get(m.etf_code),
                "target_weight": weight_map.get(m.etf_code, 0),
                "added_at": m.added_at,
            })

        # Category distribution
        category_dist = self._calculate_category_distribution(codes, weight_map)

        # Weighted performance
        performance = self._calculate_weighted_performance(indicators, weight_map)

        # Rebalance check
        rebalance_needed, rebalance_alerts = self._check_rebalance(
            pool_id, codes, weight_map
        )

        return {
            "pool_id": pool_id,
            "pool_name": pool.name,
            "member_count": len(members),
            "members": member_list,
            "category_distribution": category_dist,
            "performance": performance,
            "rebalance_needed": rebalance_needed,
            "rebalance_alerts": rebalance_alerts,
        }

    def get_correlation_matrix(self, pool_id: int) -> dict[str, Any] | None:
        """Get correlation matrix for pool members based on daily returns.

        Returns a dict with codes list and correlation matrix.
        """
        members = self._get_active_members(pool_id)
        if not members:
            return None

        codes = [m.etf_code for m in members]
        if len(codes) < 2:
            return {
                "codes": codes,
                "matrix": [[1.0]] if codes else [],
            }

        # Get daily returns for the last 60 trading days
        from app.models.etf import InstrumentDailyBar

        returns_data = {}
        for code in codes:
            bars = (
                self.db.query(InstrumentDailyBar)
                .filter(InstrumentDailyBar.etf_code == code)
                .filter(InstrumentDailyBar.change_pct.isnot(None))
                .order_by(InstrumentDailyBar.trade_date.desc())
                .limit(60)
                .all()
            )
            if bars:
                returns_data[code] = [float(b.change_pct) for b in reversed(bars)]

        # Only include codes with sufficient data
        valid_codes = [c for c in codes if c in returns_data and len(returns_data[c]) >= 20]

        if len(valid_codes) < 2:
            return {
                "codes": valid_codes,
                "matrix": [[1.0]] if valid_codes else [],
            }

        # Align data lengths
        min_len = min(len(returns_data[c]) for c in valid_codes)
        aligned = {c: returns_data[c][-min_len:] for c in valid_codes}

        # Compute correlation matrix
        n = len(valid_codes)
        matrix = [[1.0] * n for _ in range(n)]

        for i in range(n):
            for j in range(i + 1, n):
                x = np.array(aligned[valid_codes[i]])
                y = np.array(aligned[valid_codes[j]])
                if len(x) > 1 and len(y) > 1:
                    corr = np.corrcoef(x, y)[0, 1]
                    if np.isnan(corr):
                        corr = 0.0
                else:
                    corr = 0.0
                matrix[i][j] = round(float(corr), 4)
                matrix[j][i] = round(float(corr), 4)

        return {
            "codes": valid_codes,
            "matrix": matrix,
        }

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def create_snapshot(
        self, pool_id: int, snapshot_date: date | None = None
    ) -> dict[str, Any] | None:
        """Create a snapshot of pool data for a given date.

        Captures current weights, member list, and performance metrics.
        """
        pool = (
            self.db.query(ETFPools)
            .filter(ETFPools.id == pool_id)
            .filter(ETFPools.deleted_at.is_(None))
            .first()
        )
        if not pool:
            return None

        if snapshot_date is None:
            snapshot_date = date.today()

        members = self._get_active_members(pool_id)
        codes = [m.etf_code for m in members]

        # Get weights (active only)
        weights = (
            self.db.query(PoolWeight)
            .filter(
                PoolWeight.pool_id == pool_id,
                PoolWeight.etf_code.in_(codes),
                PoolWeight.removed_at.is_(None),
            )
            .all()
        )
        weight_map = {w.etf_code: float(w.target_weight) if w.target_weight else 0 for w in weights}

        # Get ETF info
        etf_info = (
            self.db.query(ETFInfo)
            .filter(ETFInfo.code.in_(codes))
            .all()
        )
        etf_name_map = {e.code: e.name for e in etf_info}
        etf_cat_map = {e.code: e.category for e in etf_info}

        # Get latest indicators
        indicators = self._get_latest_indicators(codes)
        ind_map = {ind.etf_code: ind for ind in indicators}

        # Use the latest trade date from indicator data rather than calendar date,
        # so the snapshot date is consistent with the market data it contains.
        if indicators:
            latest_trade_date = max(
                (ind.trade_date for ind in indicators if ind.trade_date),
                default=snapshot_date,
            )
            snapshot_date = latest_trade_date

        # Build holdings snapshot
        holdings = []
        for code in codes:
            ind = ind_map.get(code)
            holdings.append({
                "etf_code": code,
                "etf_name": etf_name_map.get(code),
                "category": etf_cat_map.get(code),
                "weight": weight_map.get(code, 0),
                "sharpe_1y": float(ind.sharpe_1y) if ind and ind.sharpe_1y else None,
                "volatility_20d": float(ind.volatility_20d) if ind and ind.volatility_20d else None,
                "return_1m": float(ind.return_1m) if ind and ind.return_1m else None,
                "return_3m": float(ind.return_3m) if ind and ind.return_3m else None,
                "return_1y": float(ind.return_1y) if ind and ind.return_1y else None,
            })

        # Performance metrics
        performance = self._calculate_weighted_performance(indicators, weight_map)

        snapshot_data = {
            "pool_name": pool.name,
            "member_count": len(members),
            "holdings": holdings,
            "performance": performance,
            "category_distribution": self._calculate_category_distribution(codes, weight_map),
        }

        # Check for existing snapshot on this date
        existing = (
            self.db.query(PoolSnapshot)
            .filter(
                PoolSnapshot.pool_id == pool_id,
                PoolSnapshot.snapshot_date == snapshot_date,
            )
            .first()
        )

        if existing:
            existing.data = snapshot_data
            self.db.commit()
            self.db.refresh(existing)
            snapshot = existing
        else:
            snapshot = PoolSnapshot(
                pool_id=pool_id,
                snapshot_date=snapshot_date,
                data=snapshot_data,
            )
            self.db.add(snapshot)
            self.db.commit()
            self.db.refresh(snapshot)

        return {
            "id": snapshot.id,
            "pool_id": snapshot.pool_id,
            "snapshot_date": snapshot.snapshot_date,
            "created_at": snapshot.created_at,
        }

    def get_snapshots(
        self, pool_id: int, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get recent snapshots for a pool."""
        snapshots = (
            self.db.query(PoolSnapshot)
            .filter(PoolSnapshot.pool_id == pool_id)
            .order_by(PoolSnapshot.snapshot_date.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": s.id,
                "pool_id": s.pool_id,
                "snapshot_date": s.snapshot_date,
                "created_at": s.created_at,
                "data": s.data or {},
            }
            for s in snapshots
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_active_members(self, pool_id: int) -> list[PoolMember]:
        """Get active (not soft-deleted) pool members."""
        return (
            self.db.query(PoolMember)
            .filter(PoolMember.pool_id == pool_id, PoolMember.removed_at.is_(None))
            .all()
        )

    def _get_latest_indicators(self, codes: list[str]) -> list[ETFIndicator]:
        """Get the latest indicator for each ETF code."""
        if not codes:
            return []

        # Subquery: latest indicator date per ETF
        latest_subq = (
            self.db.query(
                ETFIndicator.etf_code,
                func.max(ETFIndicator.trade_date).label("latest_date"),
            )
            .filter(ETFIndicator.etf_code.in_(codes))
            .group_by(ETFIndicator.etf_code)
            .subquery()
        )

        return (
            self.db.query(ETFIndicator)
            .join(
                latest_subq,
                (ETFIndicator.etf_code == latest_subq.c.etf_code)
                & (ETFIndicator.trade_date == latest_subq.c.latest_date),
            )
            .all()
        )

    def _calculate_category_distribution(
        self, codes: list[str], weight_map: dict[str, float]
    ) -> dict[str, Any]:
        """Calculate category distribution by weight and count."""
        etf_info = (
            self.db.query(ETFInfo)
            .filter(ETFInfo.code.in_(codes))
            .all()
        )
        cat_map = {e.code: e.category or "未分类" for e in etf_info}

        dist: dict[str, dict[str, Any]] = {}
        for code in codes:
            cat = cat_map.get(code, "未分类")
            if cat not in dist:
                dist[cat] = {"count": 0, "weight": 0.0}
            dist[cat]["count"] += 1
            dist[cat]["weight"] += weight_map.get(code, 0)

        # Round weights
        for cat in dist:
            dist[cat]["weight"] = round(dist[cat]["weight"], 2)

        return dist

    def _calculate_weighted_performance(
        self, indicators: list[ETFIndicator], weight_map: dict[str, float]
    ) -> dict[str, Any]:
        """Calculate weighted portfolio performance metrics."""
        total_weight = sum(weight_map.values())
        if total_weight == 0:
            return {}

        # Normalize weights
        norm_weights = {code: w / total_weight for code, w in weight_map.items()}

        metrics = {
            "return_1w": 0.0,
            "return_1m": 0.0,
            "return_3m": 0.0,
            "return_6m": 0.0,
            "return_1y": 0.0,
            "volatility_20d": 0.0,
            "sharpe_1y": 0.0,
            "max_drawdown_1y": 0.0,
        }

        valid_counts = {k: 0 for k in metrics}

        for ind in indicators:
            code = ind.etf_code
            w = norm_weights.get(code, 0)
            if w == 0:
                continue

            for field in metrics:
                val = getattr(ind, field)
                if val is not None:
                    metrics[field] += float(val) * w
                    valid_counts[field] += 1

        # Only include metrics with data
        result = {}
        for field, val in metrics.items():
            if valid_counts[field] > 0:
                result[field] = round(val, 4)

        return result

    def _check_rebalance(
        self,
        pool_id: int,
        codes: list[str],
        weight_map: dict[str, float],
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Check if any ETF deviates from target weight beyond threshold.

        Computes current market-value weights from latest close prices
        (assuming equal number of shares for simplicity) and compares them
        to the configured target weights.

        Returns (needs_rebalance, list of alert dicts).
        """
        close_prices = self._get_latest_close_prices(codes)

        missing_codes = set(codes) - set(close_prices.keys())
        if missing_codes:
            return False, []

        if not close_prices:
            # No price data available; cannot compute actual weights.
            return False, []

        missing_codes = set(codes) - set(close_prices.keys())
        if missing_codes:
            # Skip rebalance check when any member lacks price data; otherwise
            # the total_value denominator excludes missing ETFs and inflates
            # the actual weights of the others, producing false alerts.
            return False, []

        total_value = sum(close_prices.values())
        if total_value == 0:
            return False, []

        alerts = []
        for code in codes:
            target = float(weight_map.get(code, 0))
            actual = (close_prices.get(code, 0) / total_value) * 100.0
            deviation = abs(target - actual) / 100.0

            if deviation > self.REBALANCE_THRESHOLD:
                etf = self.db.query(ETFInfo).filter(ETFInfo.code == code).first()
                alerts.append({
                    "etf_code": code,
                    "etf_name": etf.name if etf else None,
                    "target_weight": target,
                    "actual_weight": round(actual, 2),
                    "deviation": round(deviation * 100, 2),
                })

        return len(alerts) > 0, alerts

    def _get_latest_close_prices(self, codes: list[str]) -> dict[str, float]:
        """Get the latest close price for each ETF code from daily bars."""
        from app.models.etf import InstrumentDailyBar

        if not codes:
            return {}

        latest_subq = (
            self.db.query(
                InstrumentDailyBar.etf_code,
                func.max(InstrumentDailyBar.trade_date).label("latest_date"),
            )
            .filter(InstrumentDailyBar.etf_code.in_(codes))
            .group_by(InstrumentDailyBar.etf_code)
            .subquery()
        )

        bars = (
            self.db.query(InstrumentDailyBar)
            .join(
                latest_subq,
                (InstrumentDailyBar.etf_code == latest_subq.c.etf_code)
                & (InstrumentDailyBar.trade_date == latest_subq.c.latest_date),
            )
            .all()
        )

        return {b.etf_code: float(b.close) for b in bars if b.close is not None}
