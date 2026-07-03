"""Shared fixtures for the sentiment-pipeline tests.

We deliberately avoid fakeredis (not a project dep) and instead ship a
small in-memory shim covering only the surface used by
``SentimentCache`` and ``LLMPipelineMonitor``.
"""

from __future__ import annotations

import asyncio
import fnmatch
import time
from typing import Any, Iterator

import pytest


class FakeRedis:
    """Minimal in-memory Redis stand-in.

    Supports: get, set, setex, delete, expire, incr, incrby,
    incrbyfloat, zadd, zrevrange, exists, scan_iter, eval (a tiny
    Lua-subset shim that understands ``GET``/``DEL`` for the lock
    release pattern used by ``redis_lock``).
    """

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        # Per-key TTLs (absolute monotonic timestamp). ``None`` means
        # the key never expires. The tests don't actually need to wait
        # for expiry — we just need ``expire()`` to register a TTL so
        # production semantics are mimicked.
        self.expires_at: dict[str, float | None] = {}

    # Basic
    def get(self, key: str) -> Any | None:
        v = self.store.get(key)
        if v is None:
            return None
        return v

    def set(self, key: str, value: Any, ex: int | None = None, nx: bool = False) -> Any:
        if nx and key in self.store:
            return None
        self.store[key] = str(value)
        if ex is not None:
            self.expires_at[key] = time.monotonic() + ex
        return True

    def setex(self, key: str, ttl: int, value: Any) -> bool:
        self.store[key] = str(value)
        self.expires_at[key] = time.monotonic() + ttl
        return True

    def expire(self, key: str, ttl: int) -> bool:
        if key not in self.store:
            return False
        self.expires_at[key] = time.monotonic() + ttl
        return True

    def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                self.expires_at.pop(k, None)
                n += 1
        return n

    def exists(self, key: str) -> int:
        return 1 if key in self.store else 0

    # Counters
    def incr(self, key: str) -> int:
        v = int(self.store.get(key, "0")) + 1
        self.store[key] = str(v)
        return v

    def incrby(self, key: str, n: int) -> int:
        v = int(self.store.get(key, "0")) + int(n)
        self.store[key] = str(v)
        return v

    def incrbyfloat(self, key: str, n: float) -> float:
        v = float(self.store.get(key, "0.0")) + float(n)
        self.store[key] = repr(v)
        return v

    # Sorted sets
    def zadd(self, key: str, mapping: dict[str, float]) -> int:
        z = self.zsets.setdefault(key, {})
        for m, score in mapping.items():
            z[m] = float(score)
        return len(mapping)

    def zrevrange(self, key: str, start: int, stop: int) -> list[str]:
        z = self.zsets.get(key, {})
        items = sorted(z.items(), key=lambda x: x[1], reverse=True)
        # Redis semantics: inclusive stop
        return [k for k, _ in items[start : stop + 1]]

    # Scan
    def scan_iter(self, match: str) -> Iterator[str]:
        for k in list(self.store.keys()):
            if fnmatch.fnmatchcase(k, match):
                yield k

    # Tiny Lua-subset interpreter. The only script we actually need to
    # support is the one ``redis_lock`` uses to release a lock::
    #
    #     if redis.call('get', KEYS[1]) == ARGV[1]
    #     then return redis.call('del', KEYS[1])
    #     else return 0 end
    #
    # Anything else is a no-op (returns 1 so release looks like it
    # worked and the test moves on).
    def eval(self, script: str, numkeys: int, *args: Any) -> int:
        if "del" in script and numkeys >= 1:
            key = args[0]
            expected_token = args[1] if len(args) > 1 else None
            if expected_token is not None and self.store.get(key) != str(expected_token):
                return 0
            self.delete(key)
            return 1
        return 1


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    r = FakeRedis()
    # Patch where the cache module looks it up.
    from app.core import redis_client

    monkeypatch.setattr(redis_client, "get_redis_client", lambda: r)
    return r


@pytest.fixture
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
