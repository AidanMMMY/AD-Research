"""ETF screening and ranking service.

Provides multi-condition ETF screening with dynamic filtering, sorting,
and preset configurations for common screening patterns.
"""

from typing import Any

from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session

from app.core.cache import cache_get, cache_set
from app.models.etf import ETFIndicator, ETFInfo
from app.models.scoring import ETFScore


class ScreeningService:
    """Service for ETF screening and ranking operations."""

    # Preset screening configurations
    PRESETS: dict[str, dict[str, Any]] = {
        "high_sharpe_low_vol": {
            "name": "高夏普低波动",
            "description": "夏普比率大于1.0，波动率低于20%，追求风险调整后收益",
            "filters": {
                "sharpe_min": 1.0,
                "volatility_max": 20.0,
            },
            "sort_by": "sharpe_1y",
            "sort_order": "desc",
        },
        "trend_strong": {
            "name": "趋势强势",
            "description": "RSI在50-80之间，1月收益率大于2%，趋势向上",
            "filters": {
                "rsi_min": 50.0,
                "rsi_max": 80.0,
                "return_1m_min": 2.0,
            },
            "sort_by": "return_1m",
            "sort_order": "desc",
        },
        "value_pit": {
            "name": "价值洼地",
            "description": "1年回撤大于15%，但夏普比率大于0.5，寻找反弹机会",
            "filters": {
                "sharpe_min": 0.5,
                "max_drawdown_1y_max": -15.0,
            },
            "sort_by": "return_1y",
            "sort_order": "asc",
        },
        "liquidity_sufficient": {
            "name": "流动性充足",
            "description": "20日波动率大于10%，1月收益率大于0%，确保流动性",
            "filters": {
                "volatility_min": 10.0,
                "return_1m_min": 0.0,
            },
            "sort_by": "volatility_20d",
            "sort_order": "desc",
        },
    }

    # Valid sort fields mapping: alias -> actual column name
    SORT_FIELD_MAP = {
        "composite_score": "composite_score",
        "sharpe_1y": "sharpe_1y",
        "volatility_20d": "volatility_20d",
        "return_1m": "return_1m",
        "return_3m": "return_3m",
        "return_1y": "return_1y",
        "rsi14": "rsi14",
        "rank_overall": "rank_overall",
        "rank_category": "rank_category",
        "score_return": "score_return",
        "score_risk": "score_risk",
        "score_sharpe": "score_sharpe",
        "score_liquidity": "score_liquidity",
        "score_trend": "score_trend",
    }

    def __init__(self, db: Session):
        self.db = db

    def screen(
        self,
        market: str | None = None,
        category: str | None = None,
        rsi_min: float | None = None,
        rsi_max: float | None = None,
        sharpe_min: float | None = None,
        sharpe_max: float | None = None,
        volatility_min: float | None = None,
        volatility_max: float | None = None,
        return_1m_min: float | None = None,
        return_1m_max: float | None = None,
        return_3m_min: float | None = None,
        return_3m_max: float | None = None,
        return_1y_min: float | None = None,
        return_1y_max: float | None = None,
        max_drawdown_1y_min: float | None = None,
        max_drawdown_1y_max: float | None = None,
        score_min: float | None = None,
        score_max: float | None = None,
        template_id: int | None = None,
        sort_by: str = "composite_score",
        sort_order: str = "desc",
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Screen ETFs with multiple conditions using latest indicators per ETF.

        Uses a subquery to get the most recent indicator record for each ETF,
        then applies all filter conditions and dynamic sorting.

        Args:
            market: Filter by market (e.g. SH, SZ).
            category: Filter by ETF category.
            rsi_min/max: RSI14 range filter.
            sharpe_min/max: Sharpe ratio range filter.
            volatility_min/max: Volatility range filter.
            return_1m_min/max: 1-month return range filter.
            return_3m_min/max: 3-month return range filter.
            return_1y_min/max: 1-year return range filter.
            max_drawdown_1y_min/max: 1-year max drawdown range filter.
            score_min/max: Composite score range filter.
            template_id: Filter by score template (for score-based sorting).
            sort_by: Field to sort by (see SORT_FIELD_MAP).
            sort_order: "asc" or "desc".
            offset: Pagination offset.
            limit: Pagination limit.

        Returns:
            Dict with items (list of result dicts), count, offset, limit.
        """
        cache_key = (
            f"screen:{market}:{category}:{rsi_min}:{rsi_max}:{sharpe_min}:{sharpe_max}:"
            f"{volatility_min}:{volatility_max}:{return_1m_min}:{return_1m_max}:"
            f"{return_3m_min}:{return_3m_max}:{return_1y_min}:{return_1y_max}:"
            f"{max_drawdown_1y_min}:{max_drawdown_1y_max}:"
            f"{score_min}:{score_max}:{template_id}:{sort_by}:{sort_order}:{offset}:{limit}"
        )
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        # Subquery: get the latest indicator per ETF
        latest_ind_subq = (
            self.db.query(
                ETFIndicator.etf_code,
                func.max(ETFIndicator.trade_date).label("latest_date"),
            )
            .group_by(ETFIndicator.etf_code)
            .subquery()
        )

        # Build main query joining ETFInfo, latest indicator, and optional score
        # Join order: first join the subquery (to make its columns available),
        # then join ETFIndicator using the subquery's latest_date
        query = self.db.query(ETFInfo, ETFIndicator).join(
            latest_ind_subq,
            ETFInfo.code == latest_ind_subq.c.etf_code,
        ).join(
            ETFIndicator,
            (ETFInfo.code == ETFIndicator.etf_code)
            & (ETFIndicator.trade_date == latest_ind_subq.c.latest_date),
        )

        # Auto-use default template (id=2) when sorting by score fields
        default_template_id = 2
        if template_id is None and sort_by in self.SORT_FIELD_MAP and self.SORT_FIELD_MAP.get(sort_by) in {
            "composite_score", "score_return", "score_risk", "score_sharpe",
            "score_liquidity", "score_trend", "rank_overall", "rank_category",
        }:
            template_id = default_template_id

        # Optional: join with ETFScore for score-based filtering/sorting
        score_joined = False
        if template_id is not None or score_min is not None or score_max is not None:
            # Also need latest score per ETF for the template
            latest_score_subq = (
                self.db.query(
                    ETFScore.etf_code,
                    func.max(ETFScore.trade_date).label("latest_score_date"),
                )
                .filter(ETFScore.template_id == template_id)
                .group_by(ETFScore.etf_code)
                .subquery()
            )
            # Join order matters for SQLite: subquery must be joined BEFORE
            # referencing it in ETFScore's ON clause
            query = query.outerjoin(
                latest_score_subq,
                ETFInfo.code == latest_score_subq.c.etf_code,
            ).outerjoin(
                ETFScore,
                (ETFInfo.code == ETFScore.etf_code)
                & (ETFScore.trade_date == latest_score_subq.c.latest_score_date)
                & (ETFScore.template_id == template_id),
            )
            score_joined = True

        # Apply filters
        if market:
            query = query.filter(ETFInfo.market == market)
        if category:
            query = query.filter(ETFInfo.category == category)

        # Indicator numeric filters
        if rsi_min is not None:
            query = query.filter(ETFIndicator.rsi14 >= rsi_min)
        if rsi_max is not None:
            query = query.filter(ETFIndicator.rsi14 <= rsi_max)
        if sharpe_min is not None:
            query = query.filter(ETFIndicator.sharpe_1y >= sharpe_min)
        if sharpe_max is not None:
            query = query.filter(ETFIndicator.sharpe_1y <= sharpe_max)
        if volatility_min is not None:
            query = query.filter(ETFIndicator.volatility_20d >= volatility_min)
        if volatility_max is not None:
            query = query.filter(ETFIndicator.volatility_20d <= volatility_max)
        if return_1m_min is not None:
            query = query.filter(ETFIndicator.return_1m >= return_1m_min)
        if return_1m_max is not None:
            query = query.filter(ETFIndicator.return_1m <= return_1m_max)
        if return_3m_min is not None:
            query = query.filter(ETFIndicator.return_3m >= return_3m_min)
        if return_3m_max is not None:
            query = query.filter(ETFIndicator.return_3m <= return_3m_max)
        if return_1y_min is not None:
            query = query.filter(ETFIndicator.return_1y >= return_1y_min)
        if return_1y_max is not None:
            query = query.filter(ETFIndicator.return_1y <= return_1y_max)
        if max_drawdown_1y_min is not None:
            query = query.filter(ETFIndicator.max_drawdown_1y >= max_drawdown_1y_min)
        if max_drawdown_1y_max is not None:
            query = query.filter(ETFIndicator.max_drawdown_1y <= max_drawdown_1y_max)

        # Score filters
        if score_min is not None and score_joined:
            query = query.filter(ETFScore.composite_score >= score_min)
        if score_max is not None and score_joined:
            query = query.filter(ETFScore.composite_score <= score_max)

        # Get total count before pagination
        count = query.count()

        # Apply sorting
        sort_col_name = self.SORT_FIELD_MAP.get(sort_by, "composite_score")
        sort_direction = desc if sort_order.lower() == "desc" else asc

        # Determine which table the sort column belongs to
        indicator_cols = {
            "sharpe_1y", "volatility_20d", "volatility_60d",
            "return_1m", "return_3m", "return_6m", "return_1y",
            "rsi14", "ma5", "ma10", "ma20", "ma60",
            "macd_dif", "macd_dea", "macd_hist",
            "max_drawdown_1y", "atr14", "return_1w",
        }
        score_cols = {
            "composite_score", "score_return", "score_risk",
            "score_sharpe", "score_liquidity", "score_trend",
            "rank_overall", "rank_category",
        }

        if sort_col_name in indicator_cols:
            sort_col = getattr(ETFIndicator, sort_col_name)
        elif sort_col_name in score_cols and score_joined:
            sort_col = getattr(ETFScore, sort_col_name)
        elif sort_col_name in score_cols and not score_joined:
            # Fallback to indicator column if score not joined
            fallback_map = {
                "composite_score": "sharpe_1y",
                "score_sharpe": "sharpe_1y",
                "score_return": "return_1y",
                "score_risk": "volatility_20d",
                "score_trend": "rsi14",
                "score_liquidity": "amount",
            }
            fallback = fallback_map.get(sort_col_name, "sharpe_1y")
            sort_col = getattr(ETFIndicator, fallback)
        else:
            sort_col = ETFIndicator.sharpe_1y

        query = query.order_by(sort_direction(sort_col))

        # Apply pagination
        query = query.offset(offset).limit(limit)

        # Execute and format results
        results = query.all()
        items = []
        for info, indicator in results:
            item = {
                "code": info.code,
                "name": info.name,
                "market": info.market,
                "category": info.category,
                "trade_date": indicator.trade_date.isoformat() if indicator.trade_date else None,
                "sharpe_1y": float(indicator.sharpe_1y) if indicator.sharpe_1y is not None else None,
                "volatility_20d": float(indicator.volatility_20d) if indicator.volatility_20d is not None else None,
                "rsi14": float(indicator.rsi14) if indicator.rsi14 is not None else None,
                "return_1m": float(indicator.return_1m) if indicator.return_1m is not None else None,
                "return_3m": float(indicator.return_3m) if indicator.return_3m is not None else None,
                "return_1y": float(indicator.return_1y) if indicator.return_1y is not None else None,
                "max_drawdown_1y": float(indicator.max_drawdown_1y) if indicator.max_drawdown_1y is not None else None,
            }
            # Include score data if joined
            if score_joined:
                # Access score from the query result if available
                # Since we used outerjoin, score may be None
                # We need to re-query for score data
                pass

            items.append(item)

        # If score was requested, fetch the latest score per ETF for the result set.
        if score_joined and items:
            codes = [item["code"] for item in items]
            latest_score_subq = (
                self.db.query(
                    ETFScore.etf_code,
                    func.max(ETFScore.trade_date).label("latest_score_date"),
                )
                .filter(ETFScore.etf_code.in_(codes))
                .filter(ETFScore.template_id == template_id)
                .group_by(ETFScore.etf_code)
                .subquery()
            )
            scores = (
                self.db.query(ETFScore)
                .join(
                    latest_score_subq,
                    (ETFScore.etf_code == latest_score_subq.c.etf_code)
                    & (ETFScore.trade_date == latest_score_subq.c.latest_score_date),
                )
                .filter(ETFScore.template_id == template_id)
                .all()
            )
            score_map = {s.etf_code: s for s in scores}
            for item in items:
                score = score_map.get(item["code"])
                if score:
                    item["composite_score"] = float(score.composite_score) if score.composite_score is not None else None
                    item["score_return"] = float(score.score_return) if score.score_return is not None else None
                    item["score_risk"] = float(score.score_risk) if score.score_risk is not None else None
                    item["score_sharpe"] = float(score.score_sharpe) if score.score_sharpe is not None else None
                    item["score_liquidity"] = float(score.score_liquidity) if score.score_liquidity is not None else None
                    item["score_trend"] = float(score.score_trend) if score.score_trend is not None else None
                    item["rank_overall"] = score.rank_overall
                    item["rank_category"] = score.rank_category
                else:
                    item["composite_score"] = None
                    item["score_return"] = None
                    item["score_risk"] = None
                    item["score_sharpe"] = None
                    item["score_liquidity"] = None
                    item["score_trend"] = None
                    item["rank_overall"] = None
                    item["rank_category"] = None

        result = {
            "items": items,
            "count": count,
            "offset": offset,
            "limit": limit,
        }
        cache_set(cache_key, result, ttl=300)
        return result

    def screen_by_preset(
        self,
        preset_key: str,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Screen ETFs using a preset configuration.

        Args:
            preset_key: Key from PRESETS dict.
            offset: Pagination offset.
            limit: Pagination limit.

        Returns:
            Same format as screen() with preset metadata included.
        """
        preset = self.PRESETS.get(preset_key)
        if not preset:
            return {
                "items": [],
                "count": 0,
                "offset": offset,
                "limit": limit,
                "preset": None,
            }

        filters = preset.get("filters", {})
        result = self.screen(
            **filters,
            sort_by=preset.get("sort_by", "composite_score"),
            sort_order=preset.get("sort_order", "desc"),
            offset=offset,
            limit=limit,
        )
        result["preset"] = {
            "key": preset_key,
            "name": preset["name"],
            "description": preset["description"],
        }
        return result

    def get_presets(self) -> list[dict[str, Any]]:
        """Return list of available screening presets.

        Returns:
            List of preset dicts with key, name, description, filters, sort config.
        """
        cache_key = "screen:presets"
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        presets = [
            {
                "key": key,
                "name": preset["name"],
                "description": preset["description"],
                "filters": preset.get("filters", {}),
                "sort_by": preset.get("sort_by", "composite_score"),
                "sort_order": preset.get("sort_order", "desc"),
            }
            for key, preset in self.PRESETS.items()
        ]
        cache_set(cache_key, presets, ttl=600)
        return presets

    def get_categories(self) -> list[dict[str, Any]]:
        """Return ETF categories with ETF counts.

        Returns:
            List of dicts with category name and count of active ETFs.
        """
        cache_key = "screen:categories"
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        results = (
            self.db.query(
                ETFInfo.category,
                func.count(ETFInfo.code).label("count"),
            )
            .filter(ETFInfo.status == "active")
            .group_by(ETFInfo.category)
            .order_by(desc("count"))
            .all()
        )

        categories = [
            {
                "category": cat or "未分类",
                "count": count,
            }
            for cat, count in results
        ]
        cache_set(cache_key, categories, ttl=600)
        return categories
