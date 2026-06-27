"""Redis client wrapper.

Provides a cached Redis client instance for caching, pub/sub, and
distributed locking.
"""

import contextlib
import time
from collections.abc import Generator
from contextlib import contextmanager
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


@contextmanager
def redis_lock(
    lock_name: str,
    expire_seconds: int = 300,
    wait_timeout: float | None = None,
) -> Generator[bool, None, None]:
    """A simple distributed lock using Redis.

    Usage:
        with redis_lock("my_lock") as acquired:
            if acquired:
                do_work()
            else:
                print("Could not acquire lock")

    Args:
        lock_name: Unique name for the lock.
        expire_seconds: Lock auto-expiry time to avoid deadlocks.
        wait_timeout: If None, try once and return immediately.
                      If set, retry every 0.5s until timeout.

    Yields:
        True if the lock was acquired, False otherwise.
    """
    client = get_redis_client()
    lock_key = f"lock:{lock_name}"
    token = f"{time.time()}"
    acquired = False

    def _acquire() -> bool:
        return client.set(lock_key, token, nx=True, ex=expire_seconds) is True

    if wait_timeout is None:
        acquired = _acquire()
    else:
        deadline = time.time() + wait_timeout
        while time.time() < deadline:
            acquired = _acquire()
            if acquired:
                break
            time.sleep(0.5)

    try:
        yield acquired
    finally:
        if acquired:
            # Atomically delete only if we still own the lock
            lua_script = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
            with contextlib.suppress(redis.RedisError):
                client.eval(lua_script, 1, lock_key, token)


# ── Token Blacklist Helpers ──

TOKEN_BLACKLIST_PREFIX = "bl:"


def blacklist_token(jti: str, ttl: int) -> None:
    """Add a JWT jti to the blacklist with TTL matching the token's remaining lifetime."""
    client = get_redis_client()
    client.setex(f"{TOKEN_BLACKLIST_PREFIX}{jti}", ttl, "1")


def is_token_blacklisted(jti: str) -> bool:
    """Check whether a JWT jti has been revoked."""
    client = get_redis_client()
    return client.exists(f"{TOKEN_BLACKLIST_PREFIX}{jti}") > 0
