"""Tests for the LLM failover chain (主次 LLM 自动切换, 2026-09-28).

Covers:

* ``is_quota_error`` classification — 402/401/403 always; 429 only with
  a quota marker (MiniMax 2056 / quota / insufficient / balance); plain
  429 and 5xx/timeouts are transient and must NOT fail over.
* ``FallbackProvider`` — failover on quota error, Redis cooldown shared
  state, straight-to-next while down, recovery after cooldown, keyless
  providers skipped, transient errors re-raised without failover,
  all-down → AllProvidersDownError, empty chain → placeholder.
* ``get_llm_provider`` factory — default order, LLM_PROVIDER hoist,
  keyless members excluded, legacy DeepSeek-only autodetect.

No network: stub providers + the in-memory FakeRedis from the news
test package.
"""

from __future__ import annotations

import pytest

from app.services.llm.base import LLMProvider
from app.services.llm.fallback_provider import (
    AllProvidersDownError,
    FallbackProvider,
    is_quota_error,
)
from app.tests.news.conftest import FakeRedis

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _ApiError(Exception):
    """Duck-typed stand-in for openai.APIStatusError."""

    def __init__(self, status_code: int, message: str = "") -> None:
        super().__init__(message or f"status {status_code}")
        self.status_code = status_code


class _StubProvider(LLMProvider):
    """Scriptable provider: returns a value or raises, records calls."""

    def __init__(
        self,
        result: str = "ok",
        exc: BaseException | None = None,
        available: bool = True,
    ) -> None:
        self.result = result
        self.exc = exc
        self._available = available
        self.calls = 0

    @property
    def is_available(self) -> bool:
        return self._available

    def complete(self, prompt, system=None, max_tokens=1024, temperature=0.7):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.result

    def chat(self, messages, system=None, max_tokens=1024, temperature=0.7):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.result


def _chain(*pairs, cooldown: int = 3600) -> FallbackProvider:
    return FallbackProvider(list(pairs), cooldown_sec=cooldown, redis_client=FakeRedis())


# ---------------------------------------------------------------------------
# is_quota_error
# ---------------------------------------------------------------------------


class TestQuotaClassification:
    def test_402_always_quota(self):
        assert is_quota_error(_ApiError(402, "insufficient balance")) is True

    def test_401_403_always_quota(self):
        assert is_quota_error(_ApiError(401)) is True
        assert is_quota_error(_ApiError(403)) is True

    def test_429_with_minimax_2056_is_quota(self):
        exc = _ApiError(
            429, "Error code: 429 - {'error': 2056, 'msg': '已达到 Token Plan 用量上限'}"
        )
        assert is_quota_error(exc) is True

    def test_429_with_quota_words_is_quota(self):
        assert is_quota_error(_ApiError(429, "insufficient_quota")) is True
        assert is_quota_error(_ApiError(429, "Quota exceeded")) is True

    def test_plain_429_is_transient(self):
        assert is_quota_error(_ApiError(429, "rate limit reached")) is False

    def test_5xx_and_timeout_are_transient(self):
        assert is_quota_error(_ApiError(500)) is False
        assert is_quota_error(_ApiError(503, "overloaded")) is False
        assert is_quota_error(TimeoutError("read timed out")) is False


# ---------------------------------------------------------------------------
# FallbackProvider
# ---------------------------------------------------------------------------


class TestFallbackProvider:
    def test_primary_serves_when_healthy(self):
        primary = _StubProvider("from-minimax")
        chain = _chain(("minimax", primary), ("glm", _StubProvider("from-glm")))
        assert chain.chat([{"role": "user", "content": "hi"}]) == "from-minimax"
        assert primary.calls == 1
        assert chain.last_used_provider == "minimax"

    def test_quota_error_fails_over_and_marks_down(self):
        primary = _StubProvider(exc=_ApiError(429, "2056 用量上限"))
        backup = _StubProvider("from-glm")
        chain = _chain(("minimax", primary), ("glm", backup))

        assert chain.chat([{"role": "user", "content": "hi"}]) == "from-glm"
        assert chain.down_providers() == ["minimax"]

        # While down the primary is not even attempted.
        assert chain.chat([{"role": "user", "content": "hi"}]) == "from-glm"
        assert primary.calls == 1

    def test_cooldown_expiry_retries_primary(self):
        primary = _StubProvider(exc=_ApiError(402))
        backup = _StubProvider("from-kimi")
        chain = _chain(("minimax", primary), ("kimi", backup), cooldown=60)

        assert chain.chat([{"role": "user", "content": "hi"}]) == "from-kimi"
        # Simulate the TTL passing: the in-process entry ages out and
        # Redis evicts the key (real Redis does this via EX).
        chain._local_down_until.clear()
        chain._redis.delete("llm:provider_down:minimax")
        primary.exc = None
        primary.result = "recovered"
        assert chain.chat([{"role": "user", "content": "hi"}]) == "recovered"

    def test_transient_error_raises_without_failover(self):
        primary = _StubProvider(exc=_ApiError(500, "internal error"))
        backup = _StubProvider("from-glm")
        chain = _chain(("minimax", primary), ("glm", backup))

        with pytest.raises(_ApiError):
            chain.chat([{"role": "user", "content": "hi"}])
        assert backup.calls == 0
        assert chain.down_providers() == []

    def test_plain_429_does_not_fail_over(self):
        primary = _StubProvider(exc=_ApiError(429, "rate limit"))
        backup = _StubProvider("from-glm")
        chain = _chain(("minimax", primary), ("glm", backup))

        with pytest.raises(_ApiError):
            chain.chat([{"role": "user", "content": "hi"}])
        assert backup.calls == 0
        assert chain.down_providers() == []

    def test_keyless_provider_skipped(self):
        keyless = _StubProvider(available=False)
        backup = _StubProvider("from-kimi")
        chain = _chain(("glm", keyless), ("kimi", backup))

        assert chain.chat([{"role": "user", "content": "hi"}]) == "from-kimi"
        assert keyless.calls == 0
        assert chain.is_available is True

    def test_all_providers_down_raises(self):
        primary = _StubProvider(exc=_ApiError(402))
        backup = _StubProvider(exc=_ApiError(429, "2056"))
        chain = _chain(("minimax", primary), ("glm", backup))

        # First call: both fail with quota errors → marked down, last
        # quota error propagates.
        with pytest.raises(_ApiError):
            chain.chat([{"role": "user", "content": "hi"}])
        assert set(chain.down_providers()) == {"minimax", "glm"}

        # Second call: everything is in cooldown → synthetic quota error.
        with pytest.raises(AllProvidersDownError):
            chain.chat([{"role": "user", "content": "hi"}])
        assert is_quota_error(AllProvidersDownError("x")) is True

    def test_empty_chain_returns_placeholder(self):
        chain = _chain()
        result = chain.chat([{"role": "user", "content": "hi"}])
        assert "AI 功能未配置" in result
        assert chain.is_available is False

    def test_complete_routes_same_way(self):
        primary = _StubProvider(exc=_ApiError(401))
        backup = _StubProvider("backup-done")
        chain = _chain(("minimax", primary), ("glm", backup))
        assert chain.complete("hello") == "backup-done"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestFactory:
    def test_default_chain_order_and_key_filter(self, monkeypatch):
        from app.services import llm as llm_pkg

        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.delenv("LLM_PROVIDER_CHAIN", raising=False)
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test-minimax")
        monkeypatch.setenv("GLM_API_KEY", "glm-test-key")
        monkeypatch.delenv("KIMI_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_CN_API_KEY", raising=False)

        chain = llm_pkg.get_llm_provider()
        assert isinstance(chain, FallbackProvider)
        # Kimi has no key → excluded; order preserved.
        assert chain.provider_names == ["minimax", "glm"]

    def test_legacy_llm_provider_hoisted_to_front(self, monkeypatch):
        from app.services import llm as llm_pkg

        monkeypatch.setenv("LLM_PROVIDER", "kimi")
        monkeypatch.delenv("LLM_PROVIDER_CHAIN", raising=False)
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test-minimax")
        monkeypatch.setenv("KIMI_API_KEY", "kimi-test-key")
        monkeypatch.delenv("GLM_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_CN_API_KEY", raising=False)

        chain = llm_pkg.get_llm_provider()
        assert chain.provider_names == ["kimi", "minimax"]

    def test_chain_env_reorders(self, monkeypatch):
        from app.services import llm as llm_pkg

        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.setenv("LLM_PROVIDER_CHAIN", "glm,minimax")
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test-minimax")
        monkeypatch.setenv("GLM_API_KEY", "glm-test-key")
        monkeypatch.delenv("MINIMAX_CN_API_KEY", raising=False)

        chain = llm_pkg.get_llm_provider()
        assert chain.provider_names == ["glm", "minimax"]

    def test_legacy_deepseek_only_autodetect(self, monkeypatch):
        """Pre-chain behaviour: a box with only a DeepSeek key still
        gets a working provider even though deepseek is not in the
        default chain."""
        from app.services import llm as llm_pkg

        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.delenv("LLM_PROVIDER_CHAIN", raising=False)
        for var in (
            "MINIMAX_API_KEY",
            "MINIMAX_CN_API_KEY",
            "GLM_API_KEY",
            "KIMI_API_KEY",
            "ANTHROPIC_API_KEY",
        ):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test-key")

        chain = llm_pkg.get_llm_provider()
        assert chain.provider_names == ["deepseek"]

    def test_no_keys_anywhere_gives_empty_chain(self, monkeypatch):
        from app.services import llm as llm_pkg

        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.delenv("LLM_PROVIDER_CHAIN", raising=False)
        for var in (
            "MINIMAX_API_KEY",
            "MINIMAX_CN_API_KEY",
            "GLM_API_KEY",
            "KIMI_API_KEY",
            "DEEPSEEK_API_KEY",
            "ANTHROPIC_API_KEY",
        ):
            monkeypatch.delenv(var, raising=False)

        chain = llm_pkg.get_llm_provider()
        assert chain.provider_names == []
        assert "AI 功能未配置" in chain.chat([{"role": "user", "content": "hi"}])
