"""LLM Provider abstract base class.

Defines the interface for language model providers.
"""

from abc import ABC, abstractmethod


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
