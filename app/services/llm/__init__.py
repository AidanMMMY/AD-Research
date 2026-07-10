"""LLM services package.

Provider selection is controlled by the ``LLM_PROVIDER`` env var in .env:
  - ``LLM_PROVIDER=minimax``  → MiniMax (default, global or China endpoint)
  - ``LLM_PROVIDER=deepseek`` → DeepSeek (legacy)

When unset, we probe MiniMax first and fall back to DeepSeek.
"""

import os

from app.services.llm.anthropic_provider import AnthropicProvider
from app.services.llm.base import LLMProvider
from app.services.llm.deepseek_provider import DeepSeekProvider
from app.services.llm.minimax_provider import MiniMaxProvider
from app.services.llm.llm_service import LLMService


def get_llm_provider(model: str | None = None) -> LLMProvider:
    """Factory: return the configured LLM provider based on LLM_PROVIDER env.

    Priority:
    1. ``LLM_PROVIDER=minimax``  → MiniMax
    2. ``LLM_PROVIDER=deepseek`` → DeepSeek
    3. Unset → auto-detect: MiniMax if MINIMAX_API_KEY is set, else DeepSeek
    """
    provider_name = os.getenv("LLM_PROVIDER", "").strip().lower()

    if provider_name == "minimax":
        return MiniMaxProvider(model=model)
    if provider_name == "deepseek":
        return DeepSeekProvider(model=model)

    # Auto-detect: prefer MiniMax if key is present
    if os.getenv("MINIMAX_API_KEY", "") or os.getenv("MINIMAX_CN_API_KEY", ""):
        return MiniMaxProvider(model=model)
    return DeepSeekProvider(model=model)


def check_llm_health() -> dict:
    """Check health of available LLM providers. Returns status dict for /health endpoint."""
    minimax = MiniMaxProvider()
    deepseek = DeepSeekProvider()
    return {
        "minimax_available": minimax.is_available,
        "deepseek_available": deepseek.is_available,
        "active_provider": os.getenv("LLM_PROVIDER", "auto"),
    }


__all__ = [
    "LLMProvider",
    "AnthropicProvider",
    "DeepSeekProvider",
    "MiniMaxProvider",
    "LLMService",
    "get_llm_provider",
    "check_llm_health",
]
