"""每日夜间 AI 综合研报（Daily Digest）服务子包。

- ``context``   : DigestContext 数据载体（窗口 + 8 数据包 + degraded）
- ``collector`` : DigestDataCollector 聚合层（8 包采集 + 事实清单渲染）
- ``prompts``   : 公共 system prompt + 6 章节模板
- ``generator`` : DigestGenerator 分章节 LLM 生成（重试/降级/校验）
- ``service``   : DailyDigestService 门面（聚合→生成→落库→伴随行→通知）
"""

from app.services.digest.collector import DigestDataCollector
from app.services.digest.context import DigestContext
from app.services.digest.generator import DigestGenerator, DigestResult
from app.services.digest.service import DailyDigestService

__all__ = [
    "DigestContext",
    "DigestDataCollector",
    "DigestGenerator",
    "DigestResult",
    "DailyDigestService",
]
