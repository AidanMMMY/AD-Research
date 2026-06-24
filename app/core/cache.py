"""Redis caching utilities.

Provides helpers for caching service-layer results with JSON serialization
and TTL. Keys are prefixed with ``etf:`` to avoid collisions.
"""

import json
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from app.core.redis_client import get_redis_client

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
