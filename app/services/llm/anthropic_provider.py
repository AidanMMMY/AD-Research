"""Anthropic Claude LLM provider.

Uses the Anthropic Python SDK. Requires ANTHROPIC_API_KEY env var.

Default model: claude-haiku-3-5-20241022 (cost-effective for high-volume).
Upgrade to claude-sonnet-4-20250514 for complex analysis.

When API key is not configured, the provider stays in a dormant state
that returns clear error messages instead of crashing. AI features
gracefully degrade — frontend shows a setup guide.
"""

import os

from anthropic import Anthropic

from app.services.llm.base import LLMProvider

# Default to Haiku for cost efficiency (~$0.25/MTok input, ~$1.25/MTok output)
_DEFAULT_MODEL = "claude-haiku-3-5-20241022"
_SONNET_MODEL = "claude-sonnet-4-20250514"

_NO_KEY_MSG = (
    "AI 功能未配置。请在 .env 中设置 ANTHROPIC_API_KEY。\n"
    "获取免费/付费 Key: https://console.anthropic.com/\n"
    "成本: Claude Haiku ~$0.25/百万输入 token，月均 $5-15。"
)


class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM provider.

    When ANTHROPIC_API_KEY is not set, the provider is dormant:
    all calls return a helpful setup message instead of crashing.
    """

    def __init__(self, model: str | None = None) -> None:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self._available = bool(api_key)
        self._client: Anthropic | None = None
        if self._available:
            self._client = Anthropic(api_key=api_key)
        self.model = model or _DEFAULT_MODEL

    @property
    def is_available(self) -> bool:
        """Whether the provider has a valid API key configured."""
        return self._available

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        if not self._available:
            return _NO_KEY_MSG
        if self._client is None:
            return _NO_KEY_MSG

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
        if not self._available:
            return _NO_KEY_MSG
        if self._client is None:
            return _NO_KEY_MSG

        anthropic_messages = []
        for msg in messages:
            anthropic_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

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
        return cls(model=_SONNET_MODEL)

    @classmethod
    def haiku(cls) -> "AnthropicProvider":
        return cls(model=_DEFAULT_MODEL)

    def check_health(self) -> bool:
        if not self._available:
            return False
        try:
            self.complete("ping", max_tokens=4)
            return True
        except Exception:
            return False
