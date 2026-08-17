"""Scoring system business logic service.

Provides score calculation, template management, and score queries.
"""

import logging
from datetime import date
from typing import Any

from sqlalchemy import and_, false, func, or_
from sqlalchemy.orm import Session

from app.core.cache import (
    try_cache_get,
    try_cache_invalidate_pattern,
    try_cache_set,
)
from app.data.indicators.scoring import ScoreCalculator
from app.models.etf import ETFIndicator, ETFInfo
from app.models.scoring import ETFScore, ScoreTemplate

logger = logging.getLogger(__name__)

# ``GET /scores`` 热路径原先每次请求都把 etf_score（~1M 行）GROUP BY
# 扫两遍（get_scores + count_scores 各解析一次每市场最新日期）。评分
# 每天只算一次，把 "market -> 最新评分日期" 映射缓存 10 分钟，并在
# ``calculate_daily_scores`` 完成时主动失效即可。
_LATEST_SCORE_DATES_CACHE_TTL = 600  # 10 分钟
_LATEST_SCORE_DATES_CACHE_PREFIX = "scores:latest_dates"


def _safe_float(value: Any) -> float | None:
    """Convert a value to float, returning None for invalid/missing values."""
    if value is None:
        return None
    try:
        import math

        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


# Short market codes accepted by the score-ranking API, mapped to the
# display values stored in ``etf_info.market`` ("A股" / "US"). Raw DB
# values keep working because unknown inputs pass through unchanged.
MARKET_ALIASES = {
    "cn_a": "A股",
    "a股": "A股",
    "us": "US",
    "美股": "US",
}

# Crypto instruments (etf_info.market / instrument_type == "CRYPTO") are
# excluded from the score ranking module for now (暂不纳入数字币). They
# still flow through ``calculate_daily_scores`` and remain queryable via
# the crypto detail endpoints — only the ranking query filters them out.
CRYPTO_MARKET = "CRYPTO"
CRYPTO_INSTRUMENT_TYPE = "CRYPTO"


def _normalize_market(market: str | None) -> str | None:
    """Map short market codes (cn_a / us) to ``etf_info.market`` values."""
    if market is None:
        return None
    return MARKET_ALIASES.get(market.strip().lower(), market)


def _normalize_instrument_type(instrument_type: str | None) -> str | None:
    """Normalize instrument type filter to the DB convention (ETF/STOCK)."""
    if instrument_type is None:
        return None
    return instrument_type.strip().upper()


class ScoringService:
    """Service for ETF scoring operations."""

    # Standard dimension mapping for preset templates.
    # Maps each dimension to its source metrics, default weight, and scoring direction.
    DIMENSION_MAP = {
        "return": {
            "metrics": ["return_1m", "return_3m", "return_1y"],
            "weight": 0.3,
            "direction": "asc",
        },
        "risk": {
            "metrics": ["volatility_20d", "max_drawdown_1y"],
            "weight": 0.25,
            "direction": "desc",
        },
        "sharpe": {
            "metrics": ["sharpe_1y"],
            "weight": 0.25,
            "direction": "asc",
        },
        "liquidity": {
            "metrics": ["amount"],
            "weight": 0.1,
            "direction": "asc",
        },
        "trend": {
            "metrics": ["rsi14", "ma_position"],
            "weight": 0.1,
            "direction": "asc",
        },
    }

    def __init__(self, db: Session):
        self.db = db
        self.calculator = ScoreCalculator()
        # Populated by ``calculate_daily_scores`` after each run.
        # Maps template_id → {category_bucket: [codes]}.
        self.last_buckets_used: dict[int, dict[str, list[str]]] = {}

    # ------------------------------------------------------------------
    # Template CRUD
    # ------------------------------------------------------------------

    def get_templates(self) -> list[ScoreTemplate]:
        """Get all score templates."""
        return self.db.query(ScoreTemplate).all()

    def get_template(self, template_id: int) -> ScoreTemplate | None:
        """Get a single template by ID."""
        return self.db.query(ScoreTemplate).filter(ScoreTemplate.id == template_id).first()

    def get_default_template(self) -> ScoreTemplate | None:
        """Get the default template."""
        return self.db.query(ScoreTemplate).filter(ScoreTemplate.is_default.is_(True)).first()

    def create_template(
        self,
        name: str,
        description: str,
        weights: dict[str, float],
        is_default: bool = False,
    ) -> ScoreTemplate:
        """Create a new score template."""
        template = ScoreTemplate(
            name=name,
            description=description,
            weights=weights,
            is_default=is_default,
        )
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        return template

    # ------------------------------------------------------------------
    # Daily score calculation
    # ------------------------------------------------------------------

    def calculate_daily_scores(
        self, trade_date: date | None = None
    ) -> dict[int, int]:
        """Calculate scores for all active ETFs for all templates.

        Args:
            trade_date: Date to calculate scores for. Defaults to the latest
                available indicator date per market, so a lagging market
                (e.g. A股) is not skipped when another market (e.g. US) has
                already advanced to a newer date.

        Returns:
            Dict mapping template_id to number of ETF scores calculated.
        """
        # Fetch all templates (init defaults if none exist)
        templates = self.get_templates()
        if not templates:
            self._init_default_templates()
            templates = self.get_templates()

        results: dict[int, int] = {}
        buckets_by_template: dict[int, dict[str, list[str]]] = {}

        if trade_date is not None:
            market_dates = [(None, trade_date)]
        else:
            # Latest indicator date per market. NULL markets are grouped
            # under a single None bucket.
            market_dates = (
                self.db.query(
                    ETFInfo.market,
                    func.max(ETFIndicator.trade_date).label("latest"),
                )
                .join(ETFInfo, ETFIndicator.etf_code == ETFInfo.code)
                .filter(ETFInfo.status == "active")
                .group_by(ETFInfo.market)
                .all()
            )
            if not market_dates:
                return {}

        for market, market_date in market_dates:
            indicators_query = (
                self.db.query(ETFIndicator)
                .join(ETFInfo, ETFIndicator.etf_code == ETFInfo.code)
                .filter(ETFIndicator.trade_date == market_date)
                .filter(
                    (ETFInfo.delist_date.is_(None))
                    | (ETFInfo.delist_date > market_date)
                )
            )
            if market is not None:
                indicators_query = indicators_query.filter(ETFInfo.market == market)

            indicators = indicators_query.all()
            if not indicators:
                continue

            for template in templates:
                count, buckets_used = self._calculate_scores_for_template(
                    template, indicators, market_date
                )
                results[template.id] = results.get(template.id, 0) + count
                buckets_by_template.setdefault(template.id, {}).update(buckets_used)

        # Stash the most recent buckets mapping on the instance for
        # diagnostic / API consumers. This is a side channel that does
        # NOT affect any persisted schema — callers can read
        # ``service.last_buckets_used`` after running
        # ``calculate_daily_scores``.
        self.last_buckets_used = buckets_by_template

        # 评分已推进到新交易日：主动失效 "每市场最新评分日期" 缓存，
        # 否则 GET /scores 要等 TTL（10 分钟）才看到新分数。
        try_cache_invalidate_pattern(f"{_LATEST_SCORE_DATES_CACHE_PREFIX}:*")

        return results

    def _calculate_scores_for_template(
        self,
        template: ScoreTemplate,
        indicators: list[ETFIndicator],
        trade_date: date,
    ) -> tuple[int, dict[str, list[str]]]:
        """Calculate and persist scores for a single template.

        Returns ``(count, buckets_used)`` where ``buckets_used`` maps
        each category bucket to the list of ETF codes ranked inside it.
        Codes with no category mapping fall under the ``__unknown__``
        key. This is metadata for the frontend / diagnostics and does
        not change any persisted schema.
        """
        template_weights = self._build_template_weights(template)

        # Convert ORM objects to plain dicts for the calculator.
        # Derive trend metrics that combine multiple raw indicators.
        indicator_dicts: list[dict[str, Any]] = []
        codes = [ind.etf_code for ind in indicators if ind.etf_code]
        # Look up categories once and pass them to the calculator so
        # percentile ranking happens inside category buckets. Codes
        # missing from ETFInfo fall into a __unknown__ bucket in the
        # calculator (preserving the legacy behavior of "still ranked").
        category_map = {
            e.code: e.category
            for e in self.db.query(ETFInfo).filter(ETFInfo.code.in_(codes)).all()
        } if codes else {}
        for ind in indicators:
            d = {c.name: getattr(ind, c.name) for c in ind.__table__.columns}
            d["etf_code"] = ind.etf_code
            # MA position: ratio of short-term to medium-term MA.
            # > 1 indicates price/momentum above the medium-term trend.
            ma5 = _safe_float(d.get("ma5"))
            ma20 = _safe_float(d.get("ma20"))
            if ma5 is not None and ma20 is not None and ma20 != 0:
                d["ma_position"] = ma5 / ma20
            else:
                d["ma_position"] = None
            indicator_dicts.append(d)

        # Run scoring (bucket-aware ranking is the default; pass
        # enable_bucket_aware=False in callers to fall back to the
        # legacy global ranking path).
        scores = self.calculator.calculate_scores(
            indicator_dicts,
            template_weights,
            category_map=category_map,
            enable_bucket_aware=True,
        )
        if not scores:
            return 0

        # Overall rankings
        rankings = self.calculator.rank_scores(scores)

        # Category rankings
        category_rankings = self._calculate_category_rankings(scores, indicators)

        # Build score records
        score_records: list[dict[str, Any]] = []
        for ind in indicators:
            code = ind.etf_code
            if code not in scores:
                continue

            score_data = scores[code]
            score_records.append({
                "etf_code": code,
                "trade_date": trade_date,
                "template_id": template.id,
                "composite_score": score_data.get("composite", 0),
                "score_return": score_data.get("return", 0),
                "score_risk": score_data.get("risk", 0),
                "score_sharpe": score_data.get("sharpe", 0),
                "score_liquidity": score_data.get("liquidity", 0),
                "score_trend": score_data.get("trend", 0),
                "rank_overall": rankings.get(code),
                "rank_category": category_rankings.get(code),
            })

        # Build the buckets_used map for this template run.
        buckets_used: dict[str, list[str]] = {}
        for code in scores:
            cat = category_map.get(code, "__unknown__")
            buckets_used.setdefault(cat, []).append(code)

        # Bulk insert with UPSERT (PostgreSQL on_conflict_do_update)
        if score_records:
            self._upsert_scores(score_records)

        return len(score_records), buckets_used

    def _upsert_scores(self, score_records: list[dict[str, Any]]) -> None:
        """Bulk insert ETFScore rows, updating on conflict.

        Uses PostgreSQL ``INSERT ... ON CONFLICT DO UPDATE`` when available.
        Falls back to a simple bulk insert for SQLite (used in tests).
        """
        # Convert numpy types to native Python types for PostgreSQL compatibility
        import numpy as np

        def _convert(value):
            if isinstance(value, np.integer | np.floating):
                return float(value)
            if isinstance(value, np.ndarray):
                return value.tolist()
            return value

        score_records = [
            {k: _convert(v) for k, v in record.items()} for record in score_records
        ]

        try:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = pg_insert(ETFScore).values(score_records)
            stmt = stmt.on_conflict_do_update(
                index_elements=["etf_code", "trade_date", "template_id"],
                set_={
                    "composite_score": stmt.excluded.composite_score,
                    "score_return": stmt.excluded.score_return,
                    "score_risk": stmt.excluded.score_risk,
                    "score_sharpe": stmt.excluded.score_sharpe,
                    "score_liquidity": stmt.excluded.score_liquidity,
                    "score_trend": stmt.excluded.score_trend,
                    "rank_overall": stmt.excluded.rank_overall,
                    "rank_category": stmt.excluded.rank_category,
                },
            )
            self.db.execute(stmt)
            self.db.commit()
        except ImportError:
            # SQLite fallback: delete existing + insert new
            for record in score_records:
                existing = (
                    self.db.query(ETFScore)
                    .filter(
                        ETFScore.etf_code == record["etf_code"],
                        ETFScore.trade_date == record["trade_date"],
                        ETFScore.template_id == record["template_id"],
                    )
                    .first()
                )
                if existing:
                    for key, value in record.items():
                        setattr(existing, key, value)
                else:
                    self.db.add(ETFScore(**record))
            self.db.commit()

    # ------------------------------------------------------------------
    # Weight / ranking helpers
    # ------------------------------------------------------------------

    def _build_template_weights(
        self, template: ScoreTemplate
    ) -> dict[str, dict[str, Any]]:
        """Build calculator-compatible weights from a template config."""
        weights = template.weights or {}
        result: dict[str, dict[str, Any]] = {}

        for dim_name, dim_config in self.DIMENSION_MAP.items():
            dim_weight = weights.get(dim_name, dim_config["weight"])
            if dim_weight and dim_weight > 0:
                result[dim_name] = {
                    "metrics": dim_config["metrics"],
                    "weight": dim_weight,
                    "direction": dim_config["direction"],
                }

        return result

    def _calculate_category_rankings(
        self,
        scores: dict[str, dict[str, float]],
        indicators: list[ETFIndicator],
    ) -> dict[str, int | None]:
        """Calculate per-category rankings based on composite scores."""
        codes = list(scores.keys())
        etf_info_map = {
            e.code: e.category
            for e in self.db.query(ETFInfo).filter(ETFInfo.code.in_(codes)).all()
        }

        category_groups: dict[str, list[tuple]] = {}
        for code in codes:
            cat = etf_info_map.get(code, "其他")
            category_groups.setdefault(cat, []).append(
                (code, scores[code].get("composite", 0))
            )

        category_rankings: dict[str, int | None] = {}
        for items in category_groups.values():
            sorted_items = sorted(items, key=lambda x: x[1], reverse=True)
            for rank, (code, _) in enumerate(sorted_items, 1):
                category_rankings[code] = rank

        return category_rankings

    # ------------------------------------------------------------------
    # Default templates
    # ------------------------------------------------------------------

    def _init_default_templates(self) -> None:
        """Create the three preset templates if none exist."""
        templates = [
            {
                "name": "保守型",
                "description": "注重风险控制，适合低风险偏好",
                "weights": {
                    "return": 0.2,
                    "risk": 0.35,
                    "sharpe": 0.3,
                    "liquidity": 0.1,
                    "trend": 0.05,
                },
                "is_default": False,
            },
            {
                "name": "均衡型",
                "description": "收益与风险平衡，适合中等风险偏好",
                "weights": {
                    "return": 0.3,
                    "risk": 0.25,
                    "sharpe": 0.25,
                    "liquidity": 0.1,
                    "trend": 0.1,
                },
                "is_default": True,
            },
            {
                "name": "进取型",
                "description": "追求高收益，适合高风险偏好",
                "weights": {
                    "return": 0.4,
                    "risk": 0.15,
                    "sharpe": 0.25,
                    "liquidity": 0.1,
                    "trend": 0.1,
                },
                "is_default": False,
            },
        ]

        for t in templates:
            self.create_template(**t)

    # ------------------------------------------------------------------
    # Score queries
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_ranking_filters(query, market: str | None, instrument_type: str | None):
        """Apply the shared ranking filters to a score query.

        Always excludes crypto rows (暂不纳入数字币) and optionally narrows
        by market / instrument type. ``instrument_type`` NULLs are treated
        as "ETF" (the column default) so legacy rows are not dropped.
        """
        query = query.filter(
            ETFInfo.market != CRYPTO_MARKET,
            func.coalesce(ETFInfo.instrument_type, "ETF") != CRYPTO_INSTRUMENT_TYPE,
        )
        market = _normalize_market(market)
        instrument_type = _normalize_instrument_type(instrument_type)
        if market:
            query = query.filter(ETFInfo.market == market)
        if instrument_type == "ETF":
            query = query.filter(
                func.coalesce(ETFInfo.instrument_type, "ETF") == "ETF"
            )
        elif instrument_type:
            query = query.filter(ETFInfo.instrument_type == instrument_type)
        return query

    def _latest_dates_by_market(
        self, template_id: int
    ) -> list[tuple[str | None, date | None]]:
        """Per-market latest scored trade_date, Redis-cached.

        Mirrors the per-market date resolution in
        :meth:`calculate_daily_scores` so a lagging market (e.g. A股)
        is not filtered out when another market (e.g. US) has already
        advanced to a newer date.

        2026-08-17 性能修复：原实现把这个 GROUP BY 子查询直接嵌进
        ``get_scores`` / ``count_scores``，导致 ``GET /scores`` 每次
        请求把 etf_score（~1M 行）扫两遍。评分每天只算一次，这里把
        映射结果缓存 10 分钟（``calculate_daily_scores`` 完成时主动
        失效）。缓存未命中时的 GROUP BY 走
        ``(template_id, trade_date, rank_overall)`` 索引最左前缀。
        """
        cache_key = f"{_LATEST_SCORE_DATES_CACHE_PREFIX}:{template_id}"
        cached = try_cache_get(cache_key)
        if cached is not None:
            return [
                (
                    row["market"],
                    date.fromisoformat(row["max_date"])
                    if row.get("max_date")
                    else None,
                )
                for row in cached
            ]

        rows: list[tuple[str | None, date | None]] = (
            self.db.query(
                ETFInfo.market,
                func.max(ETFScore.trade_date),
            )
            .join(ETFInfo, ETFScore.etf_code == ETFInfo.code)
            .filter(ETFScore.template_id == template_id)
            .group_by(ETFInfo.market)
            .all()
        )
        try_cache_set(
            cache_key,
            [
                {
                    "market": market,
                    "max_date": max_date.isoformat() if max_date else None,
                }
                for market, max_date in rows
            ],
            ttl=_LATEST_SCORE_DATES_CACHE_TTL,
        )
        return rows

    def _apply_latest_dates_filter(self, query, template_id: int):
        """Filter a score query to each market's latest scored date.

        语义与原 ``latest_dates`` 子查询 JOIN 完全等价：market 为 NULL
        的分组在 JOIN 里永不匹配，这里同样跳过；没有任何评分日期时
        返回恒空结果集（与原 JOIN 空子查询一致）。

        用 OR 条件替代 JOIN 子查询后，热路径在缓存命中时完全不再触碰
        GROUP BY 全扫；``(template_id, trade_date, ...)`` 索引可直接
        服务 ``template_id = ? AND trade_date IN (...)`` 的过滤。
        """
        conditions = [
            and_(ETFInfo.market == market, ETFScore.trade_date == max_date)
            for market, max_date in self._latest_dates_by_market(template_id)
            if market is not None and max_date is not None
        ]
        if not conditions:
            return query.filter(false())
        return query.filter(or_(*conditions))

    def get_scores(
        self,
        template_id: int | None = None,
        trade_date: date | None = None,
        limit: int = 50,
        market: str | None = None,
        category: str | None = None,
        instrument_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query ETF scores with optional filtering.

        Crypto instruments are always excluded from the ranking (暂不纳入
        数字币).

        Args:
            template_id: Filter by template. Defaults to the default template.
            trade_date: Filter by date. Defaults to the latest scored date
                per market (so markets on different trading calendars all
                appear with their own most recent scores).
            limit: Maximum number of results.
            market: Filter by market. Accepts short codes ("cn_a", "us")
                or the raw DB values ("A股", "US").
            category: Filter by ETF category.
            instrument_type: Filter by instrument type ("ETF" / "STOCK").

        Returns:
            List of score dicts with ETF metadata, ordered best-first.
            ``rank_overall`` is re-numbered as a continuous 1..N display
            rank within the filtered result set; the stored whole-market
            rank is preserved under ``rank_overall_original``.
        """
        if template_id is None:
            default = self.get_default_template()
            template_id = default.id if default else 1

        query = (
            self.db.query(ETFScore, ETFInfo, ETFIndicator)
            .join(ETFInfo, ETFScore.etf_code == ETFInfo.code)
            .outerjoin(
                ETFIndicator,
                (ETFScore.etf_code == ETFIndicator.etf_code)
                & (ETFScore.trade_date == ETFIndicator.trade_date),
            )
            .filter(ETFScore.template_id == template_id)
        )

        if trade_date is not None:
            query = query.filter(ETFScore.trade_date == trade_date)
        else:
            query = self._apply_latest_dates_filter(query, template_id)

        query = self._apply_ranking_filters(query, market, instrument_type)
        if category:
            query = query.filter(ETFInfo.category == category)

        query = query.order_by(ETFScore.rank_overall.asc().nullslast())
        results = query.limit(limit).all()

        output: list[dict[str, Any]] = []
        for score, info, indicator in results:
            output.append({
                "etf_code": score.etf_code,
                "etf_name": info.name,
                "name_zh": info.name_zh,
                "market": info.market,
                "category": info.category,
                "instrument_type": info.instrument_type,
                "trade_date": score.trade_date,
                "composite_score": float(score.composite_score) if score.composite_score is not None else None,
                "score_return": float(score.score_return) if score.score_return is not None else None,
                "score_risk": float(score.score_risk) if score.score_risk is not None else None,
                "score_sharpe": float(score.score_sharpe) if score.score_sharpe is not None else None,
                "score_liquidity": float(score.score_liquidity) if score.score_liquidity is not None else None,
                "score_trend": float(score.score_trend) if score.score_trend is not None else None,
                "rank_overall": score.rank_overall,
                "rank_category": score.rank_category,
                "return_1m": float(indicator.return_1m) if indicator and indicator.return_1m is not None else None,
                "return_3m": float(indicator.return_3m) if indicator and indicator.return_3m is not None else None,
                "return_1y": float(indicator.return_1y) if indicator and indicator.return_1y is not None else None,
            })

        # Re-number the display rank. The persisted ``rank_overall`` is a
        # whole-market (crypto included) sequence assigned at scoring time,
        # so excluding crypto at query time leaves gaps (1, 2, 5, ...).
        # Overwrite it with a continuous 1..N sequence within the current
        # filtered result set (the list is already ordered best-first by
        # the query above) and keep the stored value under
        # ``rank_overall_original`` for provenance.
        for display_rank, item in enumerate(output, 1):
            item["rank_overall_original"] = item["rank_overall"]
            item["rank_overall"] = display_rank

        return output

    def count_scores(
        self,
        template_id: int | None = None,
        trade_date: date | None = None,
        market: str | None = None,
        category: str | None = None,
        instrument_type: str | None = None,
    ) -> int:
        """Return the total number of scores matching the filters.

        Mirrors :meth:`get_scores` (including default template / latest
        trade date resolution / crypto exclusion) so list endpoints can
        report the real total for pagination instead of the truncated
        page size.
        """
        if template_id is None:
            default = self.get_default_template()
            template_id = default.id if default else 1

        query = (
            self.db.query(func.count(ETFScore.id))
            .join(ETFInfo, ETFScore.etf_code == ETFInfo.code)
            .filter(ETFScore.template_id == template_id)
        )

        if trade_date is not None:
            query = query.filter(ETFScore.trade_date == trade_date)
        else:
            query = self._apply_latest_dates_filter(query, template_id)
        query = self._apply_ranking_filters(query, market, instrument_type)
        if category:
            query = query.filter(ETFInfo.category == category)

        return query.scalar() or 0

    def get_latest_score(
        self,
        etf_code: str,
        market: str | None = None,
    ) -> dict[str, Any] | None:
        """Return the most recent composite score for a single instrument.

        Looks up the latest ``ETFScore`` row for the instrument under the
        default score template, optionally filtering by ``ETFInfo.market``.
        The returned dict mirrors the fields consumed by the crypto
        detail/score page.
        """
        query = (
            self.db.query(ETFScore, ETFInfo)
            .join(ETFInfo, ETFScore.etf_code == ETFInfo.code)
            .filter(ETFScore.etf_code == etf_code)
        )
        default = self.get_default_template()
        if default is not None:
            query = query.filter(ETFScore.template_id == default.id)
        if market:
            query = query.filter(ETFInfo.market == market)

        score = (
            query.order_by(ETFScore.trade_date.desc(), ETFScore.composite_score.desc())
            .first()
        )
        if score is None:
            return None

        score_obj, info = score
        return {
            "etf_code": score_obj.etf_code,
            "name": info.name if info else None,
            "name_zh": info.name_zh if info else None,
            "market": info.market if info else None,
            "trade_date": score_obj.trade_date.isoformat() if score_obj.trade_date else None,
            "composite_score": float(score_obj.composite_score) if score_obj.composite_score is not None else None,
            "score_return": float(score_obj.score_return) if score_obj.score_return is not None else None,
            "score_risk": float(score_obj.score_risk) if score_obj.score_risk is not None else None,
            "score_sharpe": float(score_obj.score_sharpe) if score_obj.score_sharpe is not None else None,
            "score_liquidity": float(score_obj.score_liquidity) if score_obj.score_liquidity is not None else None,
            "score_trend": float(score_obj.score_trend) if score_obj.score_trend is not None else None,
            "rank_overall": score_obj.rank_overall,
            "rank_category": score_obj.rank_category,
        }
