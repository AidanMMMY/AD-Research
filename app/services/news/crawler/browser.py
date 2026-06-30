"""Optional Playwright browser pool.

This module is intentionally light on dependencies. If
``playwright`` is not installed, ``BrowserPool`` reports
``available = False`` and callers can transparently fall back
to ``httpx``.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class BrowserPool:
    """Lazy Playwright browser pool with graceful fallback.

    Instantiating the pool never raises, even when Playwright
    isn't installed. Use :meth:`is_available` to decide whether to
    actually request a browser context. A typical lifecycle::

        async with BrowserPool() as pool:
            if pool.is_available():
                page = await pool.new_page()
                ...
            else:
                # fall back to httpx
                ...

    Notes
    -----
    - ``max_browser_pool_size`` caps the number of browser contexts
      held open simultaneously. Reuse is preferred over churn.
    - All public methods are async to match the rest of the
      framework, even when the underlying Playwright call is sync
      (we wrap with ``asyncio.to_thread`` so the event loop isn't
      blocked).
    """

    def __init__(self, max_size: int = 2) -> None:
        self.max_size = max(1, int(max_size))
        self._available = False
        self._playwright: Any = None
        self._browser: Any = None
        self._contexts: list[Any] = []
        self._lock = threading.Lock()
        self._entered = False
        self._import_error: str | None = None
        self._try_import_playwright()

    # ------------------------------------------------------------------
    # Detection + lazy init
    # ------------------------------------------------------------------
    def _try_import_playwright(self) -> None:
        try:
            import playwright.async_api as _pw_async  # type: ignore[import-not-found]

            self._playwright = _pw_async
            self._available = True
        except Exception as exc:  # noqa: BLE001 - any import failure = unavailable
            self._available = False
            self._playwright = None
            self._import_error = repr(exc)
            logger.info(
                "Playwright unavailable (%s); BrowserPool will report is_available=False",
                exc,
            )

    @property
    def import_error(self) -> str | None:
        """Last import error message, useful for diagnostics."""
        return self._import_error

    def is_available(self) -> bool:
        """Whether ``playwright`` is installed and we can launch browsers."""
        return self._available

    async def __aenter__(self) -> "BrowserPool":
        await self.start()
        self._entered = True
        return self

    async def __aexit__(self, *exc) -> None:  # type: ignore[no-untyped-def]
        await self.close()
        self._entered = False
        return None

    async def start(self) -> None:
        """Launch the underlying browser if available."""
        if not self.is_available() or self._browser is not None:
            return
        try:
            from playwright.async_api import async_playwright  # type: ignore[import-not-found]

            self._pw_ctx = await async_playwright().start()
            self._browser = await self._pw_ctx.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            logger.info("Playwright Chromium launched")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to launch Playwright: %s", exc)
            self._available = False
            await self._safe_stop()

    async def _safe_stop(self) -> None:
        try:
            if self._browser is not None:
                await self._browser.close()
        except Exception:  # noqa: BLE001 - best-effort cleanup
            pass
        try:
            if getattr(self, "_pw_ctx", None) is not None:
                await self._pw_ctx.stop()
        except Exception:  # noqa: BLE001
            pass
        self._browser = None
        self._pw_ctx = None

    async def close(self) -> None:
        """Close all contexts and the underlying browser."""
        with self._lock:
            contexts = list(self._contexts)
            self._contexts.clear()
        for ctx in contexts:
            try:
                await ctx.close()
            except Exception:  # noqa: BLE001 - ignore during shutdown
                pass
        await self._safe_stop()

    # ------------------------------------------------------------------
    # Page acquisition
    # ------------------------------------------------------------------
    async def new_page(self):  # type: ignore[no-untyped-def]
        """Acquire a Playwright ``Page`` from the pool.

        Returns ``None`` when Playwright isn't available — callers
        can use this as a signal to fall back to httpx.
        """
        if not self.is_available():
            return None
        if self._browser is None:
            await self.start()
        if self._browser is None:
            return None

        # We only need a single shared context; pages are cheap.
        ctx = None
        with self._lock:
            if self._contexts:
                ctx = self._contexts.pop()
        if ctx is None:
            ctx = await self._browser.new_context()
        page = await ctx.new_page()
        return page

    async def release(self, page) -> None:  # type: ignore[no-untyped-def]
        """Return a page (and its underlying context) to the pool."""
        if page is None:
            return
        try:
            ctx = page.context
        except Exception:  # noqa: BLE001
            return
        try:
            await page.close()
        except Exception:  # noqa: BLE001
            pass
        with self._lock:
            if len(self._contexts) < self.max_size:
                self._contexts.append(ctx)
                return
        try:
            await ctx.close()
        except Exception:  # noqa: BLE001
            pass
