"""Anthropic Claude LLM provider.

Uses the Anthropic Python SDK. Requires ANTHROPIC_API_KEY env var.

Default model: claude-haiku-3-5-20241022 (cost-effective for high-volume).
Upgrade to claude-sonnet-4-20250514 for complex analysis.
"""

import os

from anthropic import Anthropic

from app.services.llm.base import LLMProvider

# Default to Haiku for cost efficiency (~$0.25/MTok input)
_DEFAULT_MODEL = "claude-haiku-3-5-20241022"
# Sonnet for complex analysis (~$3/MTok input, ~$15/MTok output)
_SONNET_MODEL = "claude-sonnet-4-20250514"


class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM provider."""

    def __init__(self, model: str | None = None) -> None:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is not set. "
                "Get a key at https://console.anthropic.com/"
            )
        self._client = Anthropic(api_key=api_key)
        self.model = model or _DEFAULT_MODEL

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        """Single-prompt completion using Claude Messages API."""
        messages = [{"role": "user", "content": prompt}]

        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)
        # Extract text from first content block
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""

    def chat(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        """Multi-turn chat completion."""
        anthropic_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            anthropic_messages.append({"role": role, "content": content})

        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": anthropic_messages,
        }
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""

    @classmethod
    def sonnet(cls) -> "AnthropicProvider":
        """Create a provider instance using Claude Sonnet for complex tasks."""
        return cls(model=_SONNET_MODEL)

    @classmethod
    def haiku(cls) -> "AnthropicProvider":
        """Create a provider instance using Claude Haiku for cost-efficiency."""
        return cls(model=_DEFAULT_MODEL)

    def check_health(self) -> bool:
        """Quick health check with a minimal API call."""
        try:
            self.complete("ping", max_tokens=4)
            return True
        except Exception:
            return False
