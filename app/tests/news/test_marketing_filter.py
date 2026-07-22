"""Tests for the generic marketing content filter.

Covers :class:`MarketingContentFilter` (keyword blocklist, LLM path
with a stubbed provider, fail-open behaviour, per-source cache-key
isolation, custom system prompts) and the :class:`WechatMarketingFilter`
compatibility subclass (same behaviour as the pre-generalization
implementation).
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.news.filters.marketing_filter import (
    DEFAULT_MARKETING_KEYWORDS,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_SYSTEM_PROMPT_EN,
    MarketingContentFilter,
    MarketingVerdict,
)
from app.services.news.filters.wechat_marketing_filter import (
    _LLM_SYSTEM_PROMPT,
    WechatMarketingFilter,
)


class _StubLLMProvider:
    """Minimal stand-in for an LLM provider.

    Returns a pre-canned JSON string from :meth:`complete` and
    ``is_available=True``. Tests build an instance with a
    ``complete_return`` / ``complete_side_effect``.
    """

    def __init__(
        self,
        *,
        complete_return: str = '{"knowledge": true, "confidence": 0.9}',
        complete_side_effect: Exception | None = None,
        is_available: bool = True,
    ) -> None:
        self._complete_return = complete_return
        self._side_effect = complete_side_effect
        self._is_available = is_available
        self.calls: list[dict[str, Any]] = []

    @property
    def is_available(self) -> bool:
        return self._is_available

    def complete(self, prompt: str, system: str | None = None, **_: Any) -> str:
        self.calls.append({"prompt": prompt, "system": system})
        if self._side_effect is not None:
            raise self._side_effect
        return self._complete_return


# ---------------------------------------------------------------------------
# Generic filter — heuristic blocklist
# ---------------------------------------------------------------------------


class TestGenericFilterHeuristic:
    def test_empty_title_is_marketing(self):
        f = MarketingContentFilter(source="zerohedge", llm_enabled=False)
        verdict = f.classify("", "anything")
        assert verdict.is_knowledge is False
        assert verdict.reason == "empty_input"

    def test_default_keywords_still_applied(self):
        f = MarketingContentFilter(source="zerohedge", llm_enabled=False)
        verdict = f.classify("重磅：研学计划开启报名", "扫码加入")
        assert verdict.is_knowledge is False
        assert verdict.reason == "keyword_blocklist"

    def test_custom_keywords_override_default(self):
        f = MarketingContentFilter(
            source="zerohedge",
            keywords=("sponsored", "webinar"),
            llm_enabled=False,
        )
        verdict = f.classify("Sponsored: why you need this trading course", "body")
        assert verdict.is_knowledge is False
        assert verdict.reason == "keyword_blocklist"

    def test_custom_keywords_replace_default(self):
        """With a custom blocklist the default Chinese keywords no longer fire."""
        f = MarketingContentFilter(
            source="zerohedge",
            keywords=("sponsored",),
            llm_enabled=False,
        )
        verdict = f.classify("研学计划开启报名", "扫码加入")
        # Default keyword missed → falls through to the (disabled) LLM.
        assert verdict.is_knowledge is True
        assert verdict.reason == "llm_disabled_knowledge"

    def test_keyword_match_is_case_insensitive(self):
        f = MarketingContentFilter(source="decrypt", keywords=("Airdrop",), llm_enabled=False)
        verdict = f.classify("Huge AIRDROP incoming", "body")
        assert verdict.is_knowledge is False


# ---------------------------------------------------------------------------
# Generic filter — LLM path
# ---------------------------------------------------------------------------


class TestGenericFilterLlm:
    def test_llm_says_knowledge(self):
        provider = _StubLLMProvider(complete_return='{"knowledge": true, "confidence": 0.92}')
        f = MarketingContentFilter(source="zerohedge", llm_provider=provider)
        verdict = f.classify("The Fed's balance sheet, explained", "analysis body")
        assert verdict.is_knowledge is True
        assert verdict.reason == "llm_knowledge"
        assert verdict.confidence == pytest.approx(0.92, abs=1e-6)
        assert len(provider.calls) == 1

    def test_llm_says_marketing(self):
        provider = _StubLLMProvider(complete_return='{"knowledge": false, "confidence": 0.88}')
        f = MarketingContentFilter(source="zerohedge", llm_provider=provider)
        verdict = f.classify("Weekly market wrap", "Our take on the tape.")
        assert verdict.is_knowledge is False
        assert verdict.reason == "llm_marketing"
        assert verdict.confidence == pytest.approx(0.88, abs=1e-6)

    def test_llm_error_falls_open_to_knowledge(self):
        provider = _StubLLMProvider(complete_side_effect=RuntimeError("timeout"))
        f = MarketingContentFilter(source="zerohedge", llm_provider=provider)
        verdict = f.classify("Macro analysis", "body")
        assert verdict.is_knowledge is True
        assert verdict.reason == "llm_error_fallthrough"

    def test_llm_unavailable_falls_open(self):
        provider = _StubLLMProvider(is_available=False)
        f = MarketingContentFilter(source="zerohedge", llm_provider=provider)
        verdict = f.classify("Macro analysis", "body")
        assert verdict.is_knowledge is True
        assert verdict.reason == "llm_unavailable_fallthrough"

    def test_malformed_json_falls_open(self):
        provider = _StubLLMProvider(complete_return="I'm not JSON at all")
        f = MarketingContentFilter(source="zerohedge", llm_provider=provider)
        verdict = f.classify("Macro analysis", "body")
        assert verdict.is_knowledge is True
        assert verdict.reason == "llm_parse_error_fallthrough"


# ---------------------------------------------------------------------------
# System prompt selection
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    def test_default_prompt_is_generic_wording(self):
        assert "财经资讯文章" in DEFAULT_SYSTEM_PROMPT
        # The generic prompt must not be WeChat-specific.
        assert "微信公众号" not in DEFAULT_SYSTEM_PROMPT

    def test_default_prompt_used_when_not_overridden(self):
        provider = _StubLLMProvider()
        f = MarketingContentFilter(source="zerohedge", llm_provider=provider)
        f.classify("Macro analysis", "body")
        assert provider.calls[0]["system"] == DEFAULT_SYSTEM_PROMPT

    def test_custom_prompt_passed_to_provider(self):
        provider = _StubLLMProvider()
        f = MarketingContentFilter(
            source="zerohedge",
            llm_provider=provider,
            system_prompt=DEFAULT_SYSTEM_PROMPT_EN,
        )
        f.classify("Macro analysis", "body")
        assert provider.calls[0]["system"] == DEFAULT_SYSTEM_PROMPT_EN

    def test_english_prompt_covers_knowledge_vs_marketing(self):
        assert "knowledge" in DEFAULT_SYSTEM_PROMPT_EN
        assert "marketing" in DEFAULT_SYSTEM_PROMPT_EN


# ---------------------------------------------------------------------------
# Cache-key isolation per source
# ---------------------------------------------------------------------------


class TestCacheKeyIsolation:
    def test_cache_key_prefixed_with_source(self):
        f = MarketingContentFilter(source="zerohedge", llm_enabled=False)
        key = f._cache_key("title", "snippet")
        assert key.startswith("zerohedge:filter:")

    def test_same_article_yields_different_keys_per_source(self):
        f1 = MarketingContentFilter(source="zerohedge", llm_enabled=False)
        f2 = MarketingContentFilter(source="decrypt", llm_enabled=False)
        assert f1._cache_key("title", "snippet") != f2._cache_key("title", "snippet")

    def test_llm_verdict_cached_per_filter_instance(self):
        provider = _StubLLMProvider(complete_return='{"knowledge": true, "confidence": 0.9}')
        f = MarketingContentFilter(
            source="zerohedge", llm_provider=provider, cache_ttl_seconds=3600
        )
        f.classify("Macro analysis", "body")
        f.classify("Macro analysis", "body")
        assert len(provider.calls) == 1


# ---------------------------------------------------------------------------
# WechatMarketingFilter compatibility subclass
# ---------------------------------------------------------------------------


class TestWechatCompatLayer:
    def test_is_subclass_of_generic_filter(self):
        f = WechatMarketingFilter(llm_enabled=False)
        assert isinstance(f, MarketingContentFilter)

    def test_source_pinned_to_wechat_zeping(self):
        f = WechatMarketingFilter(llm_enabled=False)
        assert f._source == "wechat_zeping"
        assert f._cache_key("t", "s").startswith("wechat_zeping:filter:")

    def test_keeps_original_wechat_prompt(self):
        provider = _StubLLMProvider()
        f = WechatMarketingFilter(llm_provider=provider)
        f.classify("宏观分析", "正文")
        assert provider.calls[0]["system"] == _LLM_SYSTEM_PROMPT
        assert "微信公众号文章" in provider.calls[0]["system"]

    def test_default_keywords_unchanged(self):
        f = WechatMarketingFilter(llm_enabled=False)
        verdict = f.classify("重磅预告：泽平宏观研学计划开启报名", "扫码加入")
        assert verdict.is_knowledge is False
        assert verdict.reason == "keyword_blocklist"

    def test_keywords_constant_shared_with_generic_module(self):
        from app.services.news.filters import wechat_marketing_filter as compat

        assert compat.DEFAULT_MARKETING_KEYWORDS is DEFAULT_MARKETING_KEYWORDS
        assert len(DEFAULT_MARKETING_KEYWORDS) >= 10

    def test_verdict_type_shared(self):
        from app.services.news.filters import wechat_marketing_filter as compat

        assert compat.MarketingVerdict is MarketingVerdict

    def test_llm_path_behaves_like_before(self):
        provider = _StubLLMProvider(complete_return='{"knowledge": false, "confidence": 0.88}')
        f = WechatMarketingFilter(llm_provider=provider)
        verdict = f.classify("本周宏观观点速递", "对通胀、利率的最新看法。")
        assert verdict.is_knowledge is False
        assert verdict.reason == "llm_marketing"
