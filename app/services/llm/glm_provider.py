"""Zhipu GLM LLM provider via OpenAI-compatible API.

Member of the LLM fallback chain (2026-09-28, see
``fallback_provider.py``) — typically the first fallback behind MiniMax.

Env:
  - ``GLM_API_KEY``   — key from https://open.bigmodel.cn/
  - ``GLM_BASE_URL``  — default is the **Coding Plan** endpoint
    (``https://open.bigmodel.cn/api/coding/paas/v4``); regular pay-as-you-go
    keys should override to ``https://open.bigmodel.cn/api/paas/v4``.
  - ``GLM_MODEL``     — default ``glm-4.6`` (Coding Plan flagship).
"""

import os

import httpx
from openai import OpenAI

from app.services.llm.base import LLMProvider, strip_think_tags

_DEFAULT_MODEL = "glm-4.6"
_CODING_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"

_NO_KEY_MSG = (
    "AI 功能未配置。请在 .env 中设置 GLM_API_KEY。\n"
    "获取 Key: https://open.bigmodel.cn/\n"
    "模型: glm-4.6"
)


class GLMProvider(LLMProvider):
    """Zhipu GLM provider via the OpenAI-compatible endpoint."""

    def __init__(self, model: str | None = None) -> None:
        api_key = os.getenv("GLM_API_KEY", "")
        self._available = bool(api_key)

        self._client: OpenAI | None = None
        if self._available:
            self._client = OpenAI(
                api_key=api_key,
                base_url=os.getenv("GLM_BASE_URL", "") or _CODING_BASE_URL,
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
        self.model = model or os.getenv("GLM_MODEL", "") or _DEFAULT_MODEL

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
        # long-form generations like the daily digest; the model decides
        # its own output length.
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
