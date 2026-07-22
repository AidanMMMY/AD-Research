"""AI marketing filter for WeChat public-account posts (compat layer).

The implementation was generalized into
:mod:`app.services.news.filters.marketing_filter`; this module keeps
the original WeChat-specific entry points so existing callers and
tests keep working unchanged:

* :class:`WechatMarketingFilter` — :class:`MarketingContentFilter`
  subclass pinned to ``source="wechat_zeping"``, the original Chinese
  prompt (worded for 微信公众号文章), and the default keyword blocklist.
* :data:`DEFAULT_MARKETING_KEYWORDS` — re-exported for tests / docs.
* :class:`MarketingVerdict` — re-exported.
"""

from __future__ import annotations

from typing import Any

from app.services.news.filters.marketing_filter import (
    _CACHE_TTL_SECONDS,
    DEFAULT_MARKETING_KEYWORDS,
    MarketingContentFilter,
    MarketingVerdict,
)

__all__ = [
    "WechatMarketingFilter",
    "MarketingVerdict",
    "DEFAULT_MARKETING_KEYWORDS",
]


# Original DeepSeek system prompt — Chinese, opinionated, one-word
# output, worded specifically for WeChat Official-Account posts. Kept
# verbatim from the pre-generalization implementation so LLM behavior
# for the WeChat feed is unchanged.
_LLM_SYSTEM_PROMPT = (
    "你是一位中文财经内容编辑，任务是判断一篇微信公众号文章是否"
    "属于「知识 / 分析」内容。\n"
    "判定标准：\n"
    "- knowledge=true：宏观分析、市场评论、研报、政策解读、行业研究、"
    "读书笔记、作者原创观点。\n"
    "- knowledge=false：营销活动、课程报名、会议 / 直播 / 峰会邀请、"
    "付费推广、内部活动、会员招募、销售导向内容。\n"
    "只输出 JSON，不要任何解释：{\"knowledge\": true|false, \"confidence\": 0.0_to_1.0}"
)


class WechatMarketingFilter(MarketingContentFilter):
    """Two-step WeChat content classifier.

    Thin subclass of :class:`MarketingContentFilter` with the WeChat
    source tag and the original WeChat-worded system prompt. See the
    base class for the full parameter documentation.
    """

    def __init__(
        self,
        *,
        llm_provider: Any | None = None,
        keywords: tuple[str, ...] | None = None,
        llm_enabled: bool | None = None,
        cache_ttl_seconds: int = _CACHE_TTL_SECONDS,
    ) -> None:
        super().__init__(
            source="wechat_zeping",
            llm_provider=llm_provider,
            keywords=keywords,
            system_prompt=_LLM_SYSTEM_PROMPT,
            llm_enabled=llm_enabled,
            cache_ttl_seconds=cache_ttl_seconds,
        )
