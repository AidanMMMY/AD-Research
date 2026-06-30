"""Redis-backed result cache for the sentiment pipeline.

Key layout
----------

    sentiment:article:<url_hash>     - full per-article result (JSON)
                                       TTL: 30 days, never refreshed
    sentiment:retail:<symbol>:<hours>- retail aggregation result
                                       TTL: 30 minutes
    llm:calls:<YYYY-MM-DD>:<model>   - counter, calls per day per model
    llm:tokens:<YYYY-MM-DD>:<model>:<type>
                                     - counter, prompt|completion tokens
    llm:cost:<YYYY-MM-DD>            - float counter, estimated USD
    llm:cache_hits:<YYYY-MM-DD>      - counter
    llm:cache_misses:<YYYY-MM-DD>    - counter
    sentiment:hot_symbols            - sorted set, score=watch count

The class is thin: it just wraps ``app.core.redis_client.get_redis_client``
to keep key conventions in one place.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from typing import Any

from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class SentimentCache:
    """Result cache for the sentiment pipeline."""

    PREFIX_ARTICLE = "sentiment:article"
    PREFIX_RETAIL = "sentiment:retail"
    PREFIX_LLM_CALLS = "llm:calls"
    PREFIX_LLM_TOKENS = "llm:tokens"
    PREFIX_LLM_COST = "llm:cost"
    PREFIX_LLM_HITS = "llm:cache_hits"
    PREFIX_LLM_MISSES = "llm:cache_misses"
    PREFIX_HOT = "sentiment:hot_symbols"

    ARTICLE_TTL_SECONDS = 30 * 24 * 3600  # 30 days
    RETAIL_TTL_SECONDS = 30 * 60          # 30 minutes

    def __init__(self, redis_client: Any | None = None) -> None:
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Redis accessor
    # ------------------------------------------------------------------
    @property
    def redis(self) -> Any:
        if self._redis is None:
            self._redis = get_redis_client()
        return self._redis

    # ------------------------------------------------------------------
    # Key builders
    # ------------------------------------------------------------------
    @staticmethod
    def url_hash(url: str) -> str:
        return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]

    def article_key(self, url: str) -> str:
        return f"{self.PREFIX_ARTICLE}:{self.url_hash(url)}"

    def retail_key(self, symbol: str, window_hours: int) -> str:
        return f"{self.PREFIX_RETAIL}:{symbol.upper()}:{window_hours}"

    def _calls_key(self, day: date, model: str) -> str:
        return f"{self.PREFIX_LLM_CALLS}:{day.isoformat()}:{model}"

    def _tokens_key(self, day: date, model: str, kind: str) -> str:
        return f"{self.PREFIX_LLM_TOKENS}:{day.isoformat()}:{model}:{kind}"

    def _cost_key(self, day: date) -> str:
        return f"{self.PREFIX_LLM_COST}:{day.isoformat()}"

    def _hit_key(self, day: date) -> str:
        return f"{self.PREFIX_LLM_HITS}:{day.isoformat()}"

    def _miss_key(self, day: date) -> str:
        return f"{self.PREFIX_LLM_MISSES}:{day.isoformat()}"

    # ------------------------------------------------------------------
    # Article results
    # ------------------------------------------------------------------
    def get_article(self, url: str) -> dict | None:
        raw = self.redis.get(self.article_key(url))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Bad JSON in article cache for %s", url)
            return None

    def set_article(self, url: str, payload: dict) -> None:
        self.redis.setex(
            self.article_key(url),
            self.ARTICLE_TTL_SECONDS,
            json.dumps(payload, default=str),
        )

    # ------------------------------------------------------------------
    # Retail aggregation
    # ------------------------------------------------------------------
    def get_retail(self, symbol: str, window_hours: int) -> dict | None:
        raw = self.redis.get(self.retail_key(symbol, window_hours))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def set_retail(self, symbol: str, window_hours: int, payload: dict) -> None:
        self.redis.setex(
            self.retail_key(symbol, window_hours),
            self.RETAIL_TTL_SECONDS,
            json.dumps(payload, default=str),
        )

    # ------------------------------------------------------------------
    # LLM accounting
    # ------------------------------------------------------------------
    def incr_call(self, day: date, model: str, n: int = 1) -> None:
        self.redis.incrby(self._calls_key(day, model), n)

    def incr_tokens(self, day: date, model: str, kind: str, n: int) -> None:
        if n <= 0:
            return
        self.redis.incrby(self._tokens_key(day, model, kind), n)

    def incr_cost(self, day: date, usd: float) -> None:
        if usd <= 0:
            return
        # INCRBYFLOAT is the only float-increment op in Redis.
        self.redis.incrbyfloat(self._cost_key(day), float(usd))

    def incr_hit(self, day: date) -> None:
        self.redis.incr(self._hit_key(day))

    def incr_miss(self, day: date) -> None:
        self.redis.incr(self._miss_key(day))

    # ------------------------------------------------------------------
    # Read-back helpers
    # ------------------------------------------------------------------
    def daily_summary(self, day: date | None = None) -> dict:
        day = day or date.today()
        out: dict = {"date": day.isoformat(), "by_model": {}}
        total_calls = 0
        total_cost = 0.0
        # scan for the day, cheap because key space is bounded
        for key in self.redis.scan_iter(f"{self.PREFIX_LLM_CALLS}:{day.isoformat()}:*"):
            model = key.split(":")[-1]
            calls = int(self.redis.get(key) or 0)
            prompt = int(
                self.redis.get(self._tokens_key(day, model, "prompt")) or 0
            )
            completion = int(
                self.redis.get(self._tokens_key(day, model, "completion")) or 0
            )
            out["by_model"][model] = {
                "calls": calls,
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": prompt + completion,
            }
            total_calls += calls

        out["total_calls"] = total_calls
        out["total_cost_usd"] = float(
            self.redis.get(self._cost_key(day)) or 0.0
        )
        out["cache_hits"] = int(self.redis.get(self._hit_key(day)) or 0)
        out["cache_misses"] = int(self.redis.get(self._miss_key(day)) or 0)
        hits = out["cache_hits"]
        misses = out["cache_misses"]
        out["cache_hit_rate"] = (
            round(hits / (hits + misses), 4) if (hits + misses) else 0.0
        )
        return out

    # ------------------------------------------------------------------
    # Hot symbols
    # ------------------------------------------------------------------
    def add_hot_symbol(self, symbol: str, watch_count: int) -> None:
        self.redis.zadd(self.PREFIX_HOT, {symbol.upper(): watch_count})

    def top_hot_symbols(self, n: int = 50) -> list[str]:
        items = self.redis.zrevrange(self.PREFIX_HOT, 0, n - 1)
        return [s for s in items]
