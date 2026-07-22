"""Per-source content filters.

A :class:`ContentFilter` decides whether a candidate article is worth
persisting. The marketing filter lives here — it strips out
研学/课程/活动类营销推送，保留知识/分析类内容。
:mod:`marketing_filter` is the generic implementation;
:mod:`wechat_marketing_filter` is the WeChat-pinned compat subclass.
"""

from app.services.news.filters.marketing_filter import (
    DEFAULT_MARKETING_KEYWORDS,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_SYSTEM_PROMPT_EN,
    MarketingContentFilter,
    MarketingVerdict,
)
from app.services.news.filters.wechat_marketing_filter import WechatMarketingFilter

__all__ = [
    "MarketingContentFilter",
    "WechatMarketingFilter",
    "MarketingVerdict",
    "DEFAULT_MARKETING_KEYWORDS",
    "DEFAULT_SYSTEM_PROMPT",
    "DEFAULT_SYSTEM_PROMPT_EN",
]
