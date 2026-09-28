"""Failover LLM provider chain (主次 LLM 自动切换, 2026-09-28).

``FallbackProvider`` wraps an ordered list of providers behind the same
``LLMProvider`` interface, so all ~13 call sites (digest / sentiment /
translation / summary / research / AI chat …) keep calling
``get_llm_provider()`` unchanged.

Failover semantics
------------------

* **Fail over ONLY on definitive quota/billing errors** — the ones where
  retrying the same provider is guaranteed to fail again:

  - HTTP 402 (balance insufficient, e.g. DeepSeek 余额不足)
  - HTTP 401 / 403 (invalid / revoked key)
  - HTTP 429 **with a quota marker in the body** (MiniMax token-plan
    exhaustion ``2056`` / "用量上限", generic "quota"/"insufficient").
    A *plain* 429 is a per-minute rate limit — transient, the existing
    caller-side retry handles it; failing over would just drag the next
    provider into the same queue.

  5xx / timeouts / network errors are likewise re-raised untouched.

* **Cooldown with automatic recovery**: a failed provider is marked down
  in Redis (``llm:provider_down:{name}``) for
  ``LLM_PROVIDER_COOLDOWN_SEC`` (default 6h). During cooldown every call
  skips it with zero wasted requests; when the TTL expires the primary
  is tried again — a weekly-resetting token plan (MiniMax) is picked
  back up with no manual intervention. Redis is shared, so the
  scheduler / celery / web processes all see the same state; if Redis
  is unreachable an in-process map is used instead.

* **Providers without a configured key never enter the chain** (the
  factory filters them), so a keyless fallback can't shadow a working
  one with the "AI 功能未配置" placeholder. If the chain is entirely
  empty, calls return that placeholder — preserving the pre-chain
  degrade behaviour callers already special-case.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)

_DEFAULT_COOLDOWN_SEC = 6 * 3600
_REDIS_KEY_PREFIX = "llm:provider_down:"

_NO_PROVIDER_MSG = "AI 功能未配置。链路中没有可用的 LLM provider（请检查各家 API key）。"

# Body substrings that distinguish "quota exhausted" (fail over) from
# "per-minute rate limit" (transient, let the caller retry).
_QUOTA_MARKERS = (
    "2056",  # MiniMax token plan 用量上限
    "用量上限",
    "insufficient",  # insufficient balance / insufficient_quota
    "quota",
    "token plan",
    "balance",
)


def _status_code(exc: BaseException) -> int | None:
    """Best-effort HTTP status extraction (openai SDK errors carry it)."""
    code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def is_quota_error(exc: BaseException) -> bool:
    """True when the error is a definitive quota/billing/auth failure.

    Only these justify failing over to the next provider; everything
    else (5xx, timeouts, plain 429 rate limits) is transient and left to
    the callers' existing retry logic.
    """
    status = _status_code(exc)
    if status in (401, 402, 403):
        return True
    if status == 429:
        text = str(exc).lower()
        return any(marker in text for marker in _QUOTA_MARKERS)
    return False


class FallbackProvider(LLMProvider):
    """An ordered provider chain with quota-error failover + cooldown."""

    def __init__(
        self,
        providers: list[tuple[str, LLMProvider]],
        *,
        cooldown_sec: int = _DEFAULT_COOLDOWN_SEC,
        redis_client: Any | None = None,
    ) -> None:
        # ``providers`` is a list of (name, provider) in priority order.
        self._providers = providers
        self._cooldown_sec = cooldown_sec
        self._redis = redis_client
        # In-process fallback when Redis is unreachable: name -> monotonic
        # timestamp after which the provider may be retried.
        self._local_down_until: dict[str, float] = {}
        # Observability: last provider that actually served a call.
        self.last_used_provider: str | None = None

    # -- cooldown state -------------------------------------------------

    def _redis_or_none(self):
        if self._redis is not None:
            return self._redis
        try:
            from app.core.redis_client import get_redis_client

            return get_redis_client()
        except Exception:  # pragma: no cover - defensive
            return None

    def _is_down(self, name: str) -> bool:
        until = self._local_down_until.get(name)
        if until is not None and time.monotonic() < until:
            return True
        try:
            client = self._redis_or_none()
            if client is not None and client.get(f"{_REDIS_KEY_PREFIX}{name}"):
                return True
        except Exception:  # pragma: no cover - redis hiccup: treat as up
            return False
        return False

    def _mark_down(self, name: str) -> None:
        self._local_down_until[name] = time.monotonic() + self._cooldown_sec
        try:
            client = self._redis_or_none()
            if client is not None:
                client.set(f"{_REDIS_KEY_PREFIX}{name}", "1", ex=self._cooldown_sec)
        except Exception:  # pragma: no cover - local map already covers us
            pass

    # -- LLMProvider interface ------------------------------------------

    @property
    def is_available(self) -> bool:
        return any(p.is_available for _, p in self._providers)

    @property
    def provider_names(self) -> list[str]:
        return [name for name, _ in self._providers]

    def down_providers(self) -> list[str]:
        return [name for name, _ in self._providers if self._is_down(name)]

    def _call(self, method: str, *args, **kwargs) -> str:
        if not self._providers:
            return _NO_PROVIDER_MSG

        last_exc: BaseException | None = None
        for name, provider in self._providers:
            # Keyless providers return the "AI 功能未配置" placeholder
            # instead of raising — never let that shadow a working
            # fallback (the factory already filters these; this is
            # defense in depth for direct construction).
            if not provider.is_available:
                continue
            if self._is_down(name):
                continue
            try:
                result = getattr(provider, method)(*args, **kwargs)
            except Exception as exc:
                if is_quota_error(exc):
                    self._mark_down(name)
                    logger.warning(
                        "LLM provider %s quota/auth failure → cooling down %ds, "
                        "failing over: %s",
                        name,
                        self._cooldown_sec,
                        exc,
                    )
                    last_exc = exc
                    continue
                # Transient error — do NOT fail over; preserve the callers'
                # retry semantics and don't drag fallbacks into an outage.
                raise
            self.last_used_provider = name
            return result

        # Every provider either cooled down or quota-failed this call.
        if last_exc is not None:
            raise last_exc
        # All providers are in cooldown (nothing failed *this* call) —
        # surface a synthetic quota error so callers take their
        # degrade/retry path instead of treating it as success.
        raise AllProvidersDownError(f"all LLM providers in cooldown: {self.down_providers()}")

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        return self._call(
            "complete",
            prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        return self._call(
            "chat",
            messages,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def check_health(self) -> bool:
        return any(not self._is_down(name) and p.is_available for name, p in self._providers)


class AllProvidersDownError(RuntimeError):
    """Raised when every chain member is in cooldown (none was tried).

    Carries ``status_code = 429`` + a quota marker so it classifies as a
    quota error for any upstream logic that inspects it.
    """

    status_code = 429

    def __init__(self, message: str) -> None:
        super().__init__(f"quota exhausted (2056): {message}")
