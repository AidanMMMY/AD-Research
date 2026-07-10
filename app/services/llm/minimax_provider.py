"""MiniMax LLM provider via OpenAI-compatible API.

Uses the openai Python SDK with custom base_url pointing to MiniMax.
Requires MINIMAX_API_KEY env var (or MINIMAX_CN_API_KEY for China endpoint).

Default model: minimax-m3 (可通过 MINIMAX_MODEL env 覆盖)
API docs: https://platform.minimax.io/docs
"""

import os

from openai import OpenAI

from app.services.llm.base import LLMProvider

_DEFAULT_MODEL = "minimax-m3"
# Global endpoint (for users outside China)
_BASE_URL = "https://api.minimax.io/v1"
# China endpoint
_CN_BASE_URL = "https://api.minimaxi.com/v1"

_NO_KEY_MSG = (
    "AI 功能未配置。请在 .env 中设置 MINIMAX_API_KEY。\n"
    "获取 Key: https://platform.minimax.io/\n"
    "模型: minimax-m3"
)


class MiniMaxProvider(LLMProvider):
    """MiniMax LLM provider via OpenAI-compatible API.

    MiniMax's API is fully compatible with the OpenAI SDK.
    Supports both global (api.minimax.io) and China (api.minimaxi.com) endpoints.
    """

    def __init__(self, model: str | None = None) -> None:
        # Prioritize China endpoint key, then global key
        api_key = os.getenv("MINIMAX_CN_API_KEY", "") or os.getenv("MINIMAX_API_KEY", "")
        self._available = bool(api_key)

        # Use China endpoint if CN key is set, otherwise global
        use_cn = bool(os.getenv("MINIMAX_CN_API_KEY", ""))
        base_url = _CN_BASE_URL if use_cn else _BASE_URL

        self._client: OpenAI | None = None
        if self._available:
            self._client = OpenAI(
                api_key=api_key,
                base_url=base_url,
            )
        self.model = model or os.getenv("MINIMAX_MODEL", "") or _DEFAULT_MODEL

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
