"""LLM Provider abstract base class.

Defines the interface for language model providers.
"""

import re
from abc import ABC, abstractmethod

# Reasoning models (minimax-m3, GLM-4.6, kimi-k2 …) may inline their
# chain-of-thought as <think>...</think> in the content. Strip it at the
# provider boundary once so every downstream caller is clean. Unclosed
# blocks (truncated output) are stripped to end-of-text; a response that
# is ONLY a think block becomes "" so callers hit their existing
# "empty output = failure/degrade" paths. (See minimax_provider for the
# 2026-08-18 incident this comes from.)
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_UNCLOSED_RE = re.compile(r"<think>.*$", re.DOTALL | re.IGNORECASE)


def strip_think_tags(text: str) -> str:
    """Remove ``<think>`` reasoning blocks from LLM output."""
    if not text or "<think>" not in text.lower():
        return text
    stripped = _THINK_TAG_RE.sub("", text)
    stripped = _THINK_UNCLOSED_RE.sub("", stripped)
    return stripped.strip()


class LLMProvider(ABC):
    """Abstract base for LLM providers (Anthropic, OpenAI, etc.)."""

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        """Single-prompt completion. Returns the response text."""
        ...

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        """Multi-turn chat completion. Returns the response text.

        messages: list of {"role": "user"|"assistant", "content": "..."}
        """
        ...

    def check_health(self) -> bool:
        """Check if the provider is accessible. Override in subclasses."""
        return True
