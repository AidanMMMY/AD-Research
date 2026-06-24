"""DeepSeek LLM provider via OpenAI-compatible API.

Uses the openai Python SDK with custom base_url pointing to DeepSeek.
Requires DEEPSEEK_API_KEY env var.

Default model: deepseek-v4-pro
API docs: https://platform.deepseek.com/api-docs
"""

import os

from openai import OpenAI

from app.services.llm.base import LLMProvider

_DEFAULT_MODEL = "deepseek-v4-pro"
_BASE_URL = "https://api.deepseek.com"

_NO_KEY_MSG = (
    "AI 功能未配置。请在 .env 中设置 DEEPSEEK_API_KEY。\n"
    "获取 Key: https://platform.deepseek.com/\n"
    "模型: deepseek-v4-pro"
)


class DeepSeekProvider(LLMProvider):
    """DeepSeek LLM provider via OpenAI-compatible API.

    DeepSeek's API is fully compatible with the OpenAI SDK.
    max_tokens is intentionally not passed — the model decides
    its own output length, including reasoning tokens.
    """

    def __init__(self, model: str | None = None) -> None:
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self._available = bool(api_key)
        self._client: OpenAI | None = None
        if self._available:
            self._client = OpenAI(
                api_key=api_key,
                base_url=_BASE_URL,
            )
        self.model = model or _DEFAULT_MODEL

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
        if not self._available:
            return _NO_KEY_MSG
        if self._client is None:
            return _NO_KEY_MSG

        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

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

        api_messages: list[dict] = []
        if system:
            api_messages.append({"role": "system", "content": system})
        for msg in messages:
            api_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        kwargs: dict = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
        }
        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def check_health(self) -> bool:
        if not self._available:
            return False
        try:
            result = self.complete("ping")
            return bool(result and len(result) > 0)
        except Exception:
            return False
