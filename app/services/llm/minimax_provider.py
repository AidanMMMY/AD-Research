"""MiniMax LLM provider via OpenAI-compatible API.

Uses the openai Python SDK with custom base_url pointing to MiniMax.
Requires MINIMAX_API_KEY env var (or MINIMAX_CN_API_KEY for China endpoint).

Default model: minimax-m3 (可通过 MINIMAX_MODEL env 覆盖)
API docs: https://platform.minimax.io/docs
"""

import os
import re

import httpx
from openai import OpenAI

from app.services.llm.base import LLMProvider

# MiniMax 推理模型（minimax-m3 等）会把思维链以 <think>...</think> 形式
# 混在正文里返回。2026-08-18 实踩：切换 MiniMax 主链路后每日研报 35k 字
# 里一半是 think 原文直接出站。翻译管线在 app/services/news/
# translation_service.py 有自己的 _strip_think_tags，但 digest/研报/营销
# 过滤等调用方没有——统一在 provider 出口剥除，一次修复全部调用方。
# 未闭合的 think 块（输出截断）一并剥到文末；整块只有 think 时返回空串，
# 让调用方走既有的"空输出=失败/降级"路径。
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_UNCLOSED_RE = re.compile(r"<think>.*$", re.DOTALL | re.IGNORECASE)


def _strip_think(text: str) -> str:
    if not text or "<think>" not in text.lower():
        return text
    stripped = _THINK_TAG_RE.sub("", text)
    stripped = _THINK_UNCLOSED_RE.sub("", stripped)
    return stripped.strip()

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

        # Use China endpoint if:
        #   1. MINIMAX_CN_API_KEY is explicitly set, OR
        #   2. The key prefix suggests a China-issued key (sk-cp-*)
        use_cn = bool(os.getenv("MINIMAX_CN_API_KEY", ""))
        if not use_cn and api_key and api_key.startswith("sk-cp-"):
            use_cn = True
        base_url = _CN_BASE_URL if use_cn else _BASE_URL

        self._client: OpenAI | None = None
        if self._available:
            # Bounded timeout (perf audit 2026-08-06): the openai SDK default
            # (~600 s) let a slow upstream hang request-path LLM calls for
            # minutes. 60 s read is generous for long generations while still
            # failing fast.
            self._client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=httpx.Timeout(60.0, connect=10.0),
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
        return _strip_think(response.choices[0].message.content or "")

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
        return _strip_think(response.choices[0].message.content or "")

    def check_health(self) -> bool:
        if not self._available:
            return False
        try:
            result = self.complete("ping")
            return bool(result and len(result) > 0)
        except Exception:
            return False
