"""Redis client wrapper.

Provides a cached Redis client instance for caching and pub/sub.
"""

from functools import lru_cache

import redis

from app.config import get_settings


@lru_cache
def get_redis_client() -> redis.Redis:
    """Return a cached Redis client instance.

    The client decodes responses to str by default.
    """
    settings = get_settings()
    return redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )
