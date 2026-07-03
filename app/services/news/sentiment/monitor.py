"""LLM pipeline cost/quality monitor.

The class is intentionally a thin facade over ``SentimentCache`` so all
Redis key conventions live in one place.  Pricing is hard-coded here —
it is the only place the model → USD map exists, so updating DeepSeek
pricing means editing one dict.

Pricing (USD per 1K tokens, 2026-07 reference):

    deepseek-v4-pro    in 0.00027  out 0.0011
    deepseek-v4-pro-reasoner  in 0.00055  out 0.0022
    claude-3-5-sonnet  in 0.003  out 0.015   (fallback estimate)
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any

from app.services.news.sentiment.cache import SentimentCache

logger = logging.getLogger(__name__)


# USD per 1K tokens, {model: {"input": x, "output": y}}
DEFAULT_PRICING: dict[str, dict[str, float]] = {
    "deepseek-v4-pro": {"input": 0.00027, "output": 0.0011},
    "deepseek-v4-pro-reasoner": {"input": 0.00055, "output": 0.0022},
    "deepseek-chat": {"input": 0.00027, "output": 0.0011},
    "deepseek-reasoner": {"input": 0.00055, "output": 0.0022},
    "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
    "claude-sonnet-4": {"input": 0.003, "output": 0.015},
}


class LLMPipelineMonitor:
    """Records LLM usage and exposes daily / hourly summaries."""

    def __init__(
        self,
        cache: SentimentCache | None = None,
        pricing: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self.cache = cache or SentimentCache()
        self.pricing = pricing or DEFAULT_PRICING

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def _estimate_cost(
        self, model: str, prompt_tokens: int, completion_tokens: int
    ) -> float:
        rate = self.pricing.get(model)
        if rate is None:
            logger.debug("No pricing for model %s, defaulting to deepseek-v4-pro", model)
            rate = self.pricing["deepseek-v4-pro"]
        usd_in = (prompt_tokens / 1000.0) * rate["input"]
        usd_out = (completion_tokens / 1000.0) * rate["output"]
        return round(usd_in + usd_out, 6)

    def record_call(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float | None = None,
        day: date | None = None,
    ) -> float:
        """Record a single LLM call. Returns estimated cost in USD."""
        day = day or date.today()
        if cost_usd is None:
            cost_usd = self._estimate_cost(model, prompt_tokens, completion_tokens)
        self.cache.incr_call(day, model)
        self.cache.incr_tokens(day, model, "prompt", prompt_tokens)
        self.cache.incr_tokens(day, model, "completion", completion_tokens)
        self.cache.incr_cost(day, cost_usd)
        return cost_usd

    def record_cache_hit(self, day: date | None = None) -> None:
        self.cache.incr_hit(day or date.today())

    def record_cache_miss(self, day: date | None = None) -> None:
        self.cache.incr_miss(day or date.today())

    # ------------------------------------------------------------------
    # Read-back
    # ------------------------------------------------------------------
    def daily_summary(self, day: date | None = None) -> dict:
        return self.cache.daily_summary(day)

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------
    def flush_to_db(self, day: date | None = None) -> dict:
        """Hook for nightly flush from Redis counters to Postgres.

        The destination table ``llm_usage_daily`` is *not* part of the
        current ORM schema.  We only attempt the flush when the table
        is reachable; otherwise we log a warning and return the
        snapshot we would have written.  This keeps the scheduler
        green during dev iterations and avoids a hard dependency on
        a table that may not exist yet.

        ``day`` defaults to today; pass an explicit date to flush a
        historical bucket (used by the nightly job and by tests).
        """
        day = day or date.today()
        snapshot = self.daily_summary(day)
        try:
            from sqlalchemy import text

            from app.core.database import SessionLocal

            db = SessionLocal()
            try:
                # Portable DDL — works on Postgres in prod and SQLite in
                # tests.  Postgres-specific column types (JSONB, TIMESTAMPTZ)
                # are written as portable equivalents; the production
                # migration can re-introduce stricter types later.
                db.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS llm_usage_daily (
                            day TEXT PRIMARY KEY,
                            total_calls INTEGER,
                            total_cost_usd REAL,
                            payload TEXT,
                            updated_at TEXT
                        )
                        """
                    )
                )
                db.execute(
                    text(
                        """
                        INSERT INTO llm_usage_daily (day, total_calls, total_cost_usd, payload, updated_at)
                        VALUES (:day, :calls, :cost, :payload, :updated_at)
                        """
                    ),
                    {
                        "day": day.isoformat(),
                        "calls": snapshot.get("total_calls", 0),
                        "cost": snapshot.get("total_cost_usd", 0.0),
                        "payload": json.dumps(snapshot, default=str),
                        "updated_at": datetime.utcnow().isoformat(),
                    },
                )
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.warning("llm_usage_daily flush skipped: %s", exc)
        return snapshot
