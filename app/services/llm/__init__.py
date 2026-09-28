"""LLM services package.

Provider chain (2026-09-28, 主次 LLM 自动切换):
  ``get_llm_provider()`` returns a :class:`FallbackProvider` wrapping an
  ordered chain — default ``minimax → glm → kimi``. On a definitive
  quota/billing error (MiniMax 429+2056 token-plan exhaustion, 402
  balance, 401/403 key) the failing provider cools down in Redis and
  the next one serves; after ``LLM_PROVIDER_COOLDOWN_SEC`` (default 6h)
  the primary is retried automatically.

Env:
  - ``LLM_PROVIDER_CHAIN``  — comma-separated order, e.g.
    ``minimax,glm,kimi,deepseek``. Unknown names are skipped; providers
    without a configured key never enter the chain.
  - ``LLM_PROVIDER``        — legacy single-provider override; if set it
    is hoisted to the front of the chain.
  - ``LLM_PROVIDER_COOLDOWN_SEC`` — cooldown after a quota failure
    (default 21600 = 6h).
"""

import os

from app.services.llm.anthropic_provider import AnthropicProvider
from app.services.llm.base import LLMProvider
from app.services.llm.deepseek_provider import DeepSeekProvider
from app.services.llm.fallback_provider import (
    AllProvidersDownError,
    FallbackProvider,
)
from app.services.llm.glm_provider import GLMProvider
from app.services.llm.kimi_provider import KimiProvider
from app.services.llm.llm_service import LLMService
from app.services.llm.minimax_provider import MiniMaxProvider

_DEFAULT_CHAIN = ("minimax", "glm", "kimi")
_DEFAULT_COOLDOWN_SEC = 6 * 3600

_PROVIDER_CLASSES: dict[str, type[LLMProvider]] = {
    "minimax": MiniMaxProvider,
    "glm": GLMProvider,
    "kimi": KimiProvider,
    "deepseek": DeepSeekProvider,
    "anthropic": AnthropicProvider,
}


def _chain_order() -> list[str]:
    """Ordered provider names from env, with the legacy LLM_PROVIDER
    override hoisted to the front."""
    raw = os.getenv("LLM_PROVIDER_CHAIN", "")
    order = [s.strip().lower() for s in raw.split(",") if s.strip()] or list(_DEFAULT_CHAIN)
    legacy = os.getenv("LLM_PROVIDER", "").strip().lower()
    if legacy:
        order = [legacy] + [n for n in order if n != legacy]
    return order


def get_llm_provider(model: str | None = None) -> LLMProvider:
    """Factory: return the failover chain as a single ``LLMProvider``.

    Only providers with a configured API key enter the chain, so a
    keyless member can never shadow a working fallback. When nothing is
    configured the chain is empty and calls return the
    "AI 功能未配置" placeholder — the pre-chain degrade behaviour that
    callers already special-case.
    """
    providers: list[tuple[str, LLMProvider]] = []
    for name in _chain_order():
        cls = _PROVIDER_CLASSES.get(name)
        if cls is None:
            continue
        provider = cls(model=model)
        if provider.is_available:
            providers.append((name, provider))

    if not providers:
        # Legacy autodetect: the pre-chain factory fell back to DeepSeek
        # whenever MiniMax had no key. Keep that working for setups that
        # never set LLM_PROVIDER_CHAIN (e.g. a dev box with only a
        # DeepSeek key) by sweeping every known provider for a key.
        for name, cls in _PROVIDER_CLASSES.items():
            provider = cls(model=model)
            if provider.is_available:
                providers.append((name, provider))

    cooldown = int(os.getenv("LLM_PROVIDER_COOLDOWN_SEC", "") or _DEFAULT_COOLDOWN_SEC)
    return FallbackProvider(providers, cooldown_sec=cooldown)


def check_llm_health() -> dict:
    """Check health of available LLM providers. Returns status dict for /health endpoint."""
    chain = get_llm_provider()
    keyed: dict[str, bool] = {}
    for name, cls in _PROVIDER_CLASSES.items():
        try:
            keyed[f"{name}_available"] = cls().is_available
        except Exception:  # pragma: no cover - defensive
            keyed[f"{name}_available"] = False
    return {
        **keyed,
        "chain_order": _chain_order(),
        "active_chain": (chain.provider_names if isinstance(chain, FallbackProvider) else []),
        "cooling_down": (chain.down_providers() if isinstance(chain, FallbackProvider) else []),
        "last_used_provider": getattr(chain, "last_used_provider", None),
    }


__all__ = [
    "AllProvidersDownError",
    "AnthropicProvider",
    "DeepSeekProvider",
    "FallbackProvider",
    "GLMProvider",
    "KimiProvider",
    "LLMProvider",
    "LLMService",
    "MiniMaxProvider",
    "check_llm_health",
    "get_llm_provider",
]
