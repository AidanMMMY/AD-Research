"""Redis caching utilities.

Provides helpers for caching service-layer results with JSON serialization
and TTL. Keys are prefixed with ``etf:`` to avoid collisions.
"""

import json
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

DEFAULT_TTL = 300  # 5 minutes
KEY_PREFIX = "etf"


def _make_key(*parts: Any) -> str:
    """Build a colon-separated cache key."""
    return ":".join([KEY_PREFIX] + [str(p) for p in parts if p is not None])


def cache_get(key: str) -> Any | None:
    """Get a JSON-decoded value from Redis."""
    client = get_redis_client()
    value = client.get(key)
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    """Set a JSON-encoded value in Redis with TTL."""
    client = get_redis_client()
    client.setex(key, ttl, json.dumps(value, default=str))


def cache_delete(key: str) -> None:
    """Delete a key from Redis."""
    client = get_redis_client()
    client.delete(key)


def cache_invalidate_pattern(pattern: str) -> None:
    """Delete all keys matching a glob pattern."""
    client = get_redis_client()
    for key in client.scan_iter(match=pattern):
        client.delete(key)


def try_cache_get(key: str) -> Any | None:
    """Fault-tolerant :func:`cache_get` — Redis 故障时返回 None（视同未命中）。

    用于热路径（评分榜 / 分析端点）：缓存宕机不应把只读查询打成 5xx，
    回退去查 DB 即可。故障只记 debug 日志，避免刷屏。
    """
    try:
        return cache_get(key)
    except Exception as exc:
        logger.debug("cache_get(%s) failed, falling back to DB: %s", key, exc)
        return None


def try_cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    """Fault-tolerant :func:`cache_set` — Redis 故障时静默跳过写入。"""
    try:
        cache_set(key, value, ttl=ttl)
    except Exception as exc:
        logger.debug("cache_set(%s) failed, skipping: %s", key, exc)


def try_cache_invalidate_pattern(pattern: str) -> None:
    """Fault-tolerant :func:`cache_invalidate_pattern` — Redis 故障时静默跳过。"""
    try:
        cache_invalidate_pattern(pattern)
    except Exception as exc:
        logger.debug("cache_invalidate_pattern(%s) failed, skipping: %s", pattern, exc)


def cached(ttl: int = DEFAULT_TTL, key_func: Callable[..., str] | None = None):
    """Decorator that caches a function's return value in Redis.

    Args:
        ttl: Cache time-to-live in seconds.
        key_func: Optional function that receives the same arguments as the
            wrapped function and returns a cache key string. If omitted, a
            key is built from the function module/name and positional args.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                kw_parts = [
                    f"{k}={v}" for k, v in sorted(kwargs.items()) if v is not None
                ]
                cache_key = _make_key(
                    func.__module__, func.__name__, *args, *kw_parts
                )

            cached_value = cache_get(cache_key)
            if cached_value is not None:
                return cached_value

            result = func(*args, **kwargs)
            cache_set(cache_key, result, ttl=ttl)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator
