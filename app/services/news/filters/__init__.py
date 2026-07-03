"""Per-source content filters.

A :class:`ContentFilter` decides whether a candidate article is worth
persisting. The WeChat marketing filter lives here — it strips out
研学/课程/活动类营销推送，保留知识/分析类内容。
"""

from app.services.news.filters.wechat_marketing_filter import (
    DEFAULT_MARKETING_KEYWORDS,
    MarketingVerdict,
    WechatMarketingFilter,
)

__all__ = [
    "WechatMarketingFilter",
    "MarketingVerdict",
    "DEFAULT_MARKETING_KEYWORDS",
]