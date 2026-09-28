"""Moonshot Kimi LLM provider via OpenAI-compatible API.

Second fallback in the LLM provider chain (2026-09-28, see
``fallback_provider.py``), behind MiniMax and GLM.

Env:
  - ``KIMI_API_KEY``  — key from https://platform.moonshot.cn/
  - ``KIMI_BASE_URL`` — default ``https://api.moonshot.cn/v1``.
  - ``KIMI_MODEL``    — default ``kimi-k2-0905-preview``.
"""

import os

import httpx
from openai import OpenAI

from app.services.llm.base import LLMProvider, strip_think_tags

_DEFAULT_MODEL = "kimi-k2-0905-preview"
_BASE_URL = "https://api.moonshot.cn/v1"

_NO_KEY_MSG = (
    "AI 功能未配置。请在 .env 中设置 KIMI_API_KEY。\n"
    "获取 Key: https://platform.moonshot.cn/\n"
    "模型: kimi-k2"
)


class KimiProvider(LLMProvider):
    """Moonshot Kimi provider via the OpenAI-compatible endpoint."""

    def __init__(self, model: str | None = None) -> None:
        api_key = os.getenv("KIMI_API_KEY", "")
        self._available = bool(api_key)

        self._client: OpenAI | None = None
        if self._available:
            self._client = OpenAI(
                api_key=api_key,
                base_url=os.getenv("KIMI_BASE_URL", "") or _BASE_URL,
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
        self.model = model or os.getenv("KIMI_MODEL", "") or _DEFAULT_MODEL

    @property
    def is_available(self) -> bool:
        return self._available

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, system=None, max_tokens=max_tokens, temperature=temperature)

    def chat(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        if not self._available or self._client is None:
            return _NO_KEY_MSG

        api_messages: list[dict] = []
        if system:
            api_messages.append({"role": "system", "content": system})
        for msg in messages:
            api_messages.append(
                {
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                }
            )

        # max_tokens is intentionally not passed (mirrors the MiniMax /
        # DeepSeek providers): callers' values (often 1024) would clip
        # long-form generations like the daily digest.
        response = self._client.chat.completions.create(
            model=self.model,
            messages=api_messages,
            temperature=temperature,
        )
        return strip_think_tags(response.choices[0].message.content or "")

    def check_health(self) -> bool:
        if not self._available:
            return False
        try:
            result = self.complete("ping")
            return bool(result and len(result) > 0)
        except Exception:
            return False
