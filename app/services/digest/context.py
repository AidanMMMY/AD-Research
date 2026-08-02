"""Daily Digest 聚合层数据载体（2026-08-03，B2）。

``DigestContext`` 是聚合层（collector）与生成层（generator）之间的
唯一契约：

- 窗口语义：``window_end`` = report_date 当日 06:30 Asia/Shanghai，
  ``window_start`` = 前一日 06:30，半开区间 [start, end)。
- 8 个数据包字段各自为原始数据（dict/list，结构见 collector 各
  ``_collect_*`` 方法注释），单包采集失败时该字段保持 None 且包名
  记入 ``degraded``——生成层据此在 prompt 中声明数据缺失。
- ``facts`` 是各包渲染后的**紧凑中文事实清单文本**，供 prompt 直接
  拼接；保留原始数据是为了 data_snapshot_json 排障与后续章节复用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class DigestContext:
    """一次日报生成所需的全部上下文。"""

    report_date: date
    window_start: datetime  # tz-aware, Asia/Shanghai
    window_end: datetime  # tz-aware, Asia/Shanghai

    # ---- 8 数据包（原始数据；None = 该包 degraded）----
    macro: dict[str, Any] | None = None  # MacroDataService.latest_snapshot()
    sector: dict[str, Any] | None = None  # SectorRotationService.analyze_sectors()
    scores: dict[str, Any] | None = None  # {"cn_a": [...], "us": [...]} 各 top10
    fund_flow: dict[str, Any] | None = None  # {"market","sector","micro"}
    news: dict[str, Any] | None = None  # {"buckets": {cat: [...]}, "total": int}
    watchlist: dict[str, Any] | None = None  # {"primary_user","codes","items"}
    sentiment: list[dict[str, Any]] | None = None  # SentimentService.get_market_sentiment()
    sellside: list[dict[str, Any]] | None = None  # research_reports 窗口内 ≤10 条

    # 采集失败的数据包名（不阻塞整体出报）
    degraded: list[str] = field(default_factory=list)

    # 各包渲染后的紧凑中文事实清单文本（prompt 直接拼接用）
    facts: dict[str, str] = field(default_factory=dict)

    def snapshot_meta(self) -> dict[str, Any]:
        """落库 data_snapshot_json 的元数据（窗口/各包行数/degraded）。"""
        counts: dict[str, int | None] = {}
        counts["macro"] = (
            len(self.macro.get("items", [])) if self.macro is not None else None
        )
        counts["sector"] = (
            len(self.sector.get("sectors", [])) if self.sector is not None else None
        )
        if self.scores is not None:
            counts["scores"] = sum(
                len(v) for v in self.scores.values() if isinstance(v, list)
            )
        else:
            counts["scores"] = None
        if self.fund_flow is not None:
            counts["fund_flow"] = len(self.fund_flow.get("sector", []))
        else:
            counts["fund_flow"] = None
        counts["news"] = self.news.get("total") if self.news is not None else None
        counts["watchlist"] = (
            len(self.watchlist.get("items", []))
            if self.watchlist is not None
            else None
        )
        counts["sentiment"] = len(self.sentiment) if self.sentiment is not None else None
        counts["sellside"] = len(self.sellside) if self.sellside is not None else None
        return {
            "report_date": self.report_date.isoformat(),
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "package_rows": counts,
            "degraded": list(self.degraded),
        }
