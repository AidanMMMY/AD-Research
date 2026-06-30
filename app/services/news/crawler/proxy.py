"""Proxy pool with round-robin rotation.

Proxies are passed in explicitly (typically read from the
``PROXY_LIST`` env var) and ``get`` cycles through them on each
call. If the list is empty, ``get`` returns ``None`` and requests
go direct — the system stays usable without proxies.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Iterable

logger = logging.getLogger(__name__)


class ProxyPool:
    """Round-robin proxy pool.

    Parameters
    ----------
    proxies:
        Iterable of proxy URLs (e.g. ``"http://user:pass@host:port"``).
        When ``None`` or empty, ``get`` always returns ``None`` and
        the caller requests directly.
    """

    def __init__(self, proxies: Iterable[str] | None = None) -> None:
        self._proxies: list[str] = [p.strip() for p in (proxies or []) if p and p.strip()]
        # Backwards-compat: many callers expect to round-robin over an
        # explicit list, so we keep them all even when the env is unset.
        self._current = 0
        self._lock = threading.Lock()
        if not self._proxies:
            logger.debug("ProxyPool initialized with no proxies; requests will go direct")
        else:
            logger.info("ProxyPool initialized with %d proxies", len(self._proxies))

    @classmethod
    def from_env(cls, env_var: str = "PROXY_LIST") -> "ProxyPool":
        """Build a ProxyPool from a comma-separated env variable.

        The env value format is ``"http://a:1,http://b:2,..."``.
        Whitespace around entries is ignored.
        """
        raw = os.environ.get(env_var, "")
        if not raw.strip():
            return cls()
        return cls(proxies=raw.split(","))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def proxies(self) -> list[str]:
        """Snapshot of configured proxies (read-only view)."""
        return list(self._proxies)

    @property
    def size(self) -> int:
        return len(self._proxies)

    def get(self) -> str | None:
        """Return the next proxy URL, or ``None`` when none are configured."""
        if not self._proxies:
            return None
        with self._lock:
            proxy = self._proxies[self._current % len(self._proxies)]
            self._current += 1
            return proxy

    def rotate(self) -> str | None:
        """Force-advance to the next proxy.

        Useful for explicit rotation after a failed request. Returns
        the new proxy URL (or ``None``).
        """
        if not self._proxies:
            return None
        with self._lock:
            self._current = (self._current + 1) % len(self._proxies)
            return self._proxies[self._current]

    def add(self, proxy: str) -> None:
        """Append a proxy at runtime (no-op if already present)."""
        if not proxy or not proxy.strip():
            return
        with self._lock:
            if proxy not in self._proxies:
                self._proxies.append(proxy)

    def __repr__(self) -> str:
        return f"ProxyPool(size={self.size})"
